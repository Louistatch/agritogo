"""Bronze -> Silver -> Gold pipeline for external agricultural market feeds."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import re
from datetime import datetime, timezone
from statistics import median
from typing import Any

from app.database import get_db
from app.ingestion.cpc import MarketObservation


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", "" if value is None else str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


class MarketIngestionPipeline:
    """Persist market feeds with lineage, idempotency and quality gates.

    Bronze: market_raw_payloads
    Silver: market_price_staging
    Gold:   market_prices
    """

    def __init__(self, source: str = "SIM-CPC"):
        self.sb = get_db()
        self.source = source

    def _source_config(self) -> dict[str, Any]:
        try:
            rows = (
                self.sb.table("market_data_sources")
                .select("*")
                .eq("code", self.source)
                .limit(1)
                .execute()
                .data
                or []
            )
            if rows:
                return rows[0]
        except Exception:
            pass
        return {"code": self.source, "trust_weight": 1.0, "enabled": True}

    def start_run(self, source_url: str, discovery: dict[str, Any]) -> str:
        source_cfg = self._source_config()
        if source_cfg.get("enabled") is False:
            raise RuntimeError(f"Market source {self.source} is disabled")

        result = self.sb.table("market_ingestion_runs").insert({
            "source": self.source,
            "source_url": source_url,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "discovery": discovery,
        }).execute()
        return str(result.data[0]["id"])

    def save_raw_payload(
        self,
        run_id: str,
        source_url: str,
        content_type: str,
        payload_text: str,
        extraction_mode: str,
    ) -> str:
        digest = hashlib.sha256(payload_text.encode("utf-8", errors="replace")).hexdigest()
        existing = (
            self.sb.table("market_raw_payloads")
            .select("id")
            .eq("source", self.source)
            .eq("payload_hash", digest)
            .limit(1)
            .execute()
        )
        if existing.data:
            return str(existing.data[0]["id"])

        result = self.sb.table("market_raw_payloads").insert({
            "run_id": run_id,
            "source": self.source,
            "source_url": source_url,
            "content_type": content_type,
            "payload_hash": digest,
            "payload_text": payload_text[:1_000_000],
            "extraction_mode": extraction_mode,
        }).execute()
        return str(result.data[0]["id"])

    def stage(
        self,
        run_id: str,
        raw_payload_id: str,
        observations: list[MarketObservation],
    ) -> dict[str, int]:
        accepted = review = rejected = 0
        rows = []
        source_cfg = self._source_config()
        trust_weight = float(source_cfg.get("trust_weight") or 1.0)

        for obs in observations:
            if obs.quality_status == "accepted":
                accepted += 1
            elif obs.quality_status == "rejected":
                rejected += 1
            else:
                review += 1
            rows.append({
                "run_id": run_id,
                "raw_payload_id": raw_payload_id,
                "source": obs.source,
                "source_url": obs.source_url,
                "record_hash": obs.record_hash,
                "market_raw": obs.market_raw,
                "product_raw": obs.product_raw,
                "region_raw": obs.region_raw,
                "locality_raw": obs.locality_raw,
                "observed_at": obs.observed_at,
                "price": obs.price,
                "unit": obs.unit,
                "currency": obs.currency,
                "price_type": obs.price_type,
                "quality_score": obs.quality_score,
                "source_trust_weight": trust_weight,
                "effective_quality_score": round(
                    obs.quality_score * trust_weight,
                    4,
                ),
                "quality_status": obs.quality_status,
                "quality_reason": obs.quality_reason,
                "raw_record": obs.raw_record,
            })

        for start in range(0, len(rows), 250):
            chunk = rows[start:start + 250]
            if chunk:
                self.sb.table("market_price_staging").upsert(
                    chunk,
                    on_conflict="record_hash",
                ).execute()

        return {
            "staged": len(rows),
            "accepted": accepted,
            "needs_review": review,
            "rejected": rejected,
        }

    def _aliases(self) -> dict[tuple[str, str], dict[str, Any]]:
        try:
            rows = (
                self.sb.table("market_entity_aliases")
                .select("*")
                .eq("source", self.source)
                .eq("active", True)
                .execute()
                .data
                or []
            )
        except Exception:
            rows = []
        return {
            (row["entity_type"], _norm(row["raw_value"])): row
            for row in rows
        }

    def _cultures(self) -> dict[str, dict[str, Any]]:
        rows = self.sb.table("cultures").select("id,name").execute().data or []
        return {_norm(row["name"]): row for row in rows}

    def _market_regions(self) -> dict[str, str]:
        rows = (
            self.sb.table("market_prices")
            .select("market_name,region_id")
            .not_.is_("region_id", "null")
            .limit(5000)
            .execute()
            .data
            or []
        )
        mapping: dict[str, str] = {}
        for row in rows:
            if row.get("market_name") and row.get("region_id"):
                mapping.setdefault(_norm(row["market_name"]), str(row["region_id"]))
        return mapping

    def _anomaly_check(
        self,
        culture_id: str,
        market_name: str,
        price: float,
        unit: str,
    ) -> tuple[str, float, str | None]:
        """Detect suspicious jumps with robust statistics.

        The gate is deliberately conservative: it quarantines a record for
        review rather than deleting it. With little history, the record passes
        and receives an "insufficient_history" marker.
        """
        try:
            history = (
                self.sb.table("market_prices")
                .select("price,unit")
                .eq("culture_id", culture_id)
                .eq("market_name", market_name)
                .eq("data_kind", "observation")
                .order("observed_at", desc=True)
                .limit(60)
                .execute()
                .data
                or []
            )
        except Exception:
            return "unchecked", 0.0, "history_query_failed"

        comparable = [
            float(row["price"])
            for row in history
            if row.get("price") is not None
            and (row.get("unit") or "unknown") == unit
            and float(row["price"]) > 0
        ]
        if len(comparable) < 6:
            return "insufficient_history", 0.0, None

        center = median(comparable)
        deviations = [abs(value - center) for value in comparable]
        mad = median(deviations)
        ratio = price / center if center > 0 else 1.0

        if mad > 0:
            score = 0.6745 * abs(price - center) / mad
        else:
            score = abs(ratio - 1.0) * 10.0

        suspicious = score > 8.0 or ratio > 2.5 or ratio < 0.4
        if suspicious:
            reason = (
                f"robust_outlier: score={score:.2f}, "
                f"ratio_to_median={ratio:.2f}, median={center:.2f}"
            )
            return "suspicious", round(score, 3), reason

        return "normal", round(score, 3), None

    def promote(self, run_id: str) -> dict[str, int]:
        """Promote accepted staged observations when product/market mapping is safe."""
        staged = (
            self.sb.table("market_price_staging")
            .select("*")
            .eq("run_id", run_id)
            .eq("quality_status", "accepted")
            .execute()
            .data
            or []
        )

        aliases = self._aliases()
        cultures = self._cultures()
        market_regions = self._market_regions()

        promoted = unresolved_product = unresolved_market = quarantined = 0
        errors = 0

        for row in staged:
            product_norm = _norm(row["product_raw"])
            market_norm = _norm(row["market_raw"])

            product_alias = aliases.get(("product", product_norm))
            market_alias = aliases.get(("market", market_norm))

            culture_id = None
            product_name = row["product_raw"]
            if product_alias and product_alias.get("culture_id"):
                culture_id = product_alias["culture_id"]
                product_name = product_alias.get("canonical_value") or product_name
            elif product_norm in cultures:
                culture_id = cultures[product_norm]["id"]
                product_name = cultures[product_norm]["name"]

            region_id = None
            market_name = row["market_raw"]
            if market_alias:
                region_id = market_alias.get("region_id")
                market_name = market_alias.get("canonical_value") or market_name
            if not region_id:
                region_id = market_regions.get(_norm(market_name))

            if not culture_id:
                unresolved_product += 1
                self._mark_stage(row["id"], "needs_mapping", "unresolved_product")
                continue
            if not region_id:
                unresolved_market += 1
                self._mark_stage(
                    row["id"],
                    "needs_mapping",
                    "unresolved_market",
                )
                continue

            unit = row.get("unit") or "unknown"
            anomaly_status, anomaly_score, anomaly_reason = self._anomaly_check(
                str(culture_id),
                market_name,
                float(row["price"]),
                unit,
            )
            if anomaly_status == "suspicious":
                quarantined += 1
                self._mark_stage(
                    row["id"],
                    "needs_review",
                    anomaly_reason,
                    market_canonical=market_name,
                    product_canonical=product_name,
                    anomaly_status=anomaly_status,
                    anomaly_score=anomaly_score,
                )
                continue

            payload = {
                "culture_id": culture_id,
                "region_id": region_id,
                "market_name": market_name,
                "price": row["price"],
                "unit": unit,
                "currency": row.get("currency") or "FCFA",
                "verified": True,
                "source": self.source,
                "source_url": row.get("source_url"),
                "observed_at": row["observed_at"],
                "created_at": row["observed_at"] + "T12:00:00+00:00",
                "data_kind": "observation",
                "source_record_hash": row["record_hash"],
                "price_type": row.get("price_type") or "unknown",
                "quality_score": row.get("effective_quality_score")
                or row.get("quality_score"),
                "source_trust_weight": row.get("source_trust_weight") or 1.0,
                "anomaly_score": anomaly_score,
                "anomaly_status": anomaly_status,
                "ingestion_run_id": run_id,
            }

            try:
                self.sb.table("market_prices").upsert(
                    payload,
                    on_conflict="source_record_hash",
                ).execute()
                promoted += 1
                self._mark_stage(
                    row["id"],
                    "promoted",
                    None,
                    market_canonical=market_name,
                    product_canonical=product_name,
                    anomaly_status=anomaly_status,
                    anomaly_score=anomaly_score,
                )
            except Exception as exc:
                errors += 1
                self._mark_stage(row["id"], "error", str(exc)[:500])

        return {
            "promoted": promoted,
            "unresolved_product": unresolved_product,
            "unresolved_market": unresolved_market,
            "quarantined": quarantined,
            "errors": errors,
        }

    def _mark_stage(
        self,
        stage_id: str,
        status: str,
        reason: str | None,
        *,
        market_canonical: str | None = None,
        product_canonical: str | None = None,
        anomaly_status: str | None = None,
        anomaly_score: float | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "quality_status": status,
            "quality_reason": reason,
        }
        if market_canonical is not None:
            payload["market_canonical"] = market_canonical
        if product_canonical is not None:
            payload["product_canonical"] = product_canonical
        if anomaly_status is not None:
            payload["anomaly_status"] = anomaly_status
        if anomaly_score is not None:
            payload["anomaly_score"] = anomaly_score
        self.sb.table("market_price_staging").update(payload).eq(
            "id",
            stage_id,
        ).execute()

    def finish_run(
        self,
        run_id: str,
        *,
        staged: dict[str, int],
        promoted: dict[str, int],
        endpoint: str,
        extraction_mode: str,
        error: str | None = None,
    ) -> None:
        status = "failed" if error else "success"
        if not error and promoted.get("errors"):
            status = "partial"
        self.sb.table("market_ingestion_runs").update({
            "status": status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "endpoint_used": endpoint,
            "extraction_mode": extraction_mode,
            "staged_count": staged.get("staged", 0),
            "promoted_count": promoted.get("promoted", 0),
            "review_count": (
                staged.get("needs_review", 0)
                + promoted.get("unresolved_product", 0)
                + promoted.get("unresolved_market", 0)
                + promoted.get("quarantined", 0)
            ),
            "rejected_count": staged.get("rejected", 0),
            "error": error,
        }).eq("id", run_id).execute()

        try:
            latest = (
                self.sb.table("market_price_staging")
                .select("observed_at")
                .eq("run_id", run_id)
                .order("observed_at", desc=True)
                .limit(1)
                .execute()
                .data
                or []
            )
            source_update: dict[str, Any] = {
                "last_status": status,
                "last_error": error,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if status in {"success", "partial"}:
                source_update["last_success_at"] = datetime.now(
                    timezone.utc,
                ).isoformat()
            if latest:
                source_update["last_observation_at"] = latest[0][
                    "observed_at"
                ]
            self.sb.table("market_data_sources").update(
                source_update,
            ).eq("code", self.source).execute()
        except Exception:
            pass
