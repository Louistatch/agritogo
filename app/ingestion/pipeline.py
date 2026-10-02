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
from app.ingestion.cpc import MarketObservation, culture_candidates


# Régions administratives de la source qui ne sont pas l'une des 5 régions de la
# plateforme. DAGL = District Autonome du Grand Lomé, rattaché à la région Maritime.
# Orthographes du « département » (= préfecture) de la source qui diffèrent de la table.
_PREFECTURE_SYNONYMS = {"tandjouare": "tandjoare"}

_REGION_SYNONYMS = {
    "dagl": "maritime",
    "grandlome": "maritime",
    "lome": "maritime",
}


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

        # Un relevé déjà publié ne repart pas en file : sans cela chaque passage
        # (toutes les 6 h) re-promouvrait des milliers de lignes identiques.
        published: set[str] = set()
        hashes = [row["record_hash"] for row in rows]
        for start in range(0, len(hashes), 200):
            found = (
                self.sb.table("market_price_staging")
                .select("record_hash,quality_status")
                .in_("record_hash", hashes[start:start + 200])
                .execute()
                .data
                or []
            )
            published.update(
                item["record_hash"]
                for item in found
                if item.get("quality_status") == "promoted"
            )
        rows = [row for row in rows if row["record_hash"] not in published]

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

    def _regions(self) -> dict[str, str]:
        """Nom de région normalisé -> id (table `regions`, 5 lignes)."""
        rows = self.sb.table("regions").select("id,name").execute().data or []
        return {_norm(row["name"]): str(row["id"]) for row in rows}

    def _geo_tables(self) -> dict[str, Any]:
        """Préfectures et cantons de la plateforme, pour situer un marché."""
        prefectures = (
            self.sb.table("prefectures").select("id,name,region_id").execute().data or []
        )
        cantons = (
            self.sb.table("cantons").select("id,name,prefecture_id").execute().data or []
        )
        return {
            "prefectures": {_norm(p["name"]): p for p in prefectures},
            "prefecture_by_id": {str(p["id"]): p for p in prefectures},
            "cantons": cantons,
        }

    def _resolve_geo(
        self,
        row: dict[str, Any],
        geo: dict[str, Any],
    ) -> tuple[str | None, str | None, str | None]:
        """(préfecture, canton, région) d'un relevé, d'après le découpage de la source.

        La source donne région / département / commune / localité pour chaque
        relevé. Le canton se cherche par le nom du MARCHÉ puis de la commune
        (jamais par la « localité », saisie de façon peu fiable : « Kara » pour
        Kémérida). Un marché sans canton connu en reçoit un, rattaché à sa
        préfecture. La hiérarchie de la plateforme fait foi : préfecture et région
        suivent le canton retrouvé.
        """
        raw = row.get("raw_record") or {}
        if not isinstance(raw, dict):
            return None, None, None
        dep_key = _norm(raw.get("departement"))
        dep_key = _PREFECTURE_SYNONYMS.get(dep_key, dep_key)
        pref = geo["prefectures"].get(dep_key)
        pref_id = str(pref["id"]) if pref else None

        market = row.get("market_raw") or raw.get("marche") or ""
        wanted = [_norm(market), _norm(raw.get("commune"))]
        canton = None
        for key in wanted:
            if not key:
                continue
            matches = [c for c in geo["cantons"] if _norm(c["name"]) == key]
            if matches:
                canton = next(
                    (c for c in matches if str(c["prefecture_id"]) == pref_id),
                    matches[0],
                )
                break

        if canton is None and pref_id and market:
            name = market if market != market.upper() else market.title()
            try:
                created = (
                    self.sb.table("cantons")
                    .insert({"prefecture_id": pref_id, "name": name})
                    .execute()
                    .data
                )
                if created:
                    canton = created[0]
                    geo["cantons"].append(canton)
            except Exception:
                canton = None

        if canton is not None:
            pref_id = str(canton["prefecture_id"])
        final_pref = geo["prefecture_by_id"].get(pref_id or "")
        region_id = str(final_pref["region_id"]) if final_pref else None
        return pref_id, (str(canton["id"]) if canton else None), region_id

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
        # Historique lu UNE fois par couple culture / marché pour tout le lot, puis
        # complété à mesure des publications (milliers de lignes par passage).
        cache = self.__dict__.setdefault("_history_cache", {})
        key = (culture_id, market_name)
        if key not in cache:
            try:
                cache[key] = (
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
        history = cache[key]

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

        # Un historique très régulier (MAD proche de 0) donne un score énorme pour
        # un écart minime : 1,07 fois la médiane est classé « aberrant » (score 25).
        # Le score seul ne suffit donc pas, il faut aussi un écart réel.
        # Seul un écart réel à la médiane (x2,5 ou /2,5) est suspect. Le score
        # robuste reste enregistré à titre indicatif : sur un historique très
        # régulier ou très court il s'emballe pour des variations normales
        # (1,9 fois la médiane = un marché plus cher, pas une erreur).
        suspicious = ratio > 2.5 or ratio < 0.4
        if suspicious:
            reason = (
                f"robust_outlier: score={score:.2f}, "
                f"ratio_to_median={ratio:.2f}, median={center:.2f}"
            )
            return "suspicious", round(score, 3), reason

        return "normal", round(score, 3), None

    def promote(self, run_id: str) -> dict[str, int]:
        """Promote accepted staged observations when product/market mapping is safe.

        PostgREST plafonne une réponse à 1000 lignes. Au premier passage complet,
        711 relevés restaient « accepted » sans jamais être lus. On traite donc
        par lots de 1000 : une ligne traitée quitte l'état « accepted », le lot
        suivant donne les suivantes. Garde-fous : arrêt si un lot ne fait aucun
        progrès (même identifiants qu'avant) et plafond de 30 lots.
        """
        totals = {
            "promoted": 0,
            "unresolved_product": 0,
            "unresolved_market": 0,
            "quarantined": 0,
            "errors": 0,
        }
        previous_ids: set[str] = set()
        for _ in range(30):
            batch = (
                self.sb.table("market_price_staging")
                .select("*")
                .eq("run_id", run_id)
                .eq("quality_status", "accepted")
                .limit(1000)
                .execute()
                .data
                or []
            )
            ids = {str(row["id"]) for row in batch}
            if not batch or ids == previous_ids:
                break
            previous_ids = ids
            result = self._promote_rows(run_id, batch)
            for key in totals:
                totals[key] += result.get(key, 0)
        return totals

    def _promote_rows(
        self,
        run_id: str,
        staged: list[dict[str, Any]],
    ) -> dict[str, int]:
        aliases = self._aliases()
        cultures = self._cultures()
        regions = self._regions()
        market_regions = self._market_regions()
        try:
            geo = self._geo_tables()
        except Exception:
            geo = None

        # Contrôle de plausibilité par produit sur le lot : un prix très éloigné
        # de la médiane de son produit (7 143 F/kg pour du maïs, 33 F/kg pour du
        # haricot) est presque sûrement un autre conditionnement (sac, tas) ou une
        # faute de saisie. Il part en revue, il n'est pas publié.
        by_family: dict[str, list[float]] = {}
        for item in staged:
            family = (item.get("product_raw") or "").split()[:1]
            if family and item.get("price") is not None:
                by_family.setdefault(_norm(family[0]), []).append(float(item["price"]))
        medians = {
            family: median(values)
            for family, values in by_family.items()
            if len(values) >= 5
        }

        promoted = unresolved_product = unresolved_market = quarantined = 0
        errors = 0
        pending: list[tuple[dict[str, Any], dict[str, Any], str, str, str, float]] = []

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
            else:
                for candidate in culture_candidates(row):
                    if candidate in cultures:
                        culture_id = cultures[candidate]["id"]
                        product_name = cultures[candidate]["name"]
                        break

            region_id = None
            market_name = row["market_raw"]
            if market_alias:
                region_id = market_alias.get("region_id")
                market_name = market_alias.get("canonical_value") or market_name
            if not region_id:
                region_id = market_regions.get(_norm(market_name))
            if not region_id and row.get("region_raw"):
                # La source donne la région (« PLATEAUX ») : on s'en sert pour un
                # marché encore inconnu plutôt que de le laisser sans région.
                region_key = _norm(row["region_raw"])
                region_id = regions.get(region_key) or regions.get(
                    _REGION_SYNONYMS.get(region_key, ""),
                )

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

            family_norm = _norm((row.get("product_raw") or "").split()[0]) if (row.get("product_raw") or "").split() else ""
            family_median = medians.get(family_norm)
            if family_median and family_median > 0:
                ratio = float(row["price"]) / family_median
                if ratio > 3.0 or ratio < 0.35:
                    quarantined += 1
                    self._mark_stage(
                        row["id"],
                        "needs_review",
                        f"implausible_vs_batch: ratio_to_median={ratio:.2f}, median={family_median:.0f}",
                        market_canonical=market_name,
                        product_canonical=product_name,
                    )
                    continue

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
                "price": round(float(row["price"])),
                "unit": unit,
                "currency": row.get("currency") or "FCFA",
                # Prix d'une source externe : publié mais NON vérifié par la
                # plateforme. L'application l'affiche avec la mention de sa source.
                "verified": False,
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
            if geo is not None:
                pref_id, canton_id, geo_region = self._resolve_geo(row, geo)
                if pref_id:
                    payload["prefecture_id"] = pref_id
                if canton_id:
                    payload["canton_id"] = canton_id
                if geo_region:
                    payload["region_id"] = geo_region

            pending.append((row, payload, market_name, product_name, anomaly_status, anomaly_score))
            # L'historique du lot se complète au fil des publications.
            self.__dict__.setdefault("_history_cache", {}).setdefault(
                (str(culture_id), market_name), [],
            ).append({"price": payload["price"], "unit": unit})

        # Publication par paquets : des milliers de relevés, un appel par paquet
        # plutôt qu'un par ligne. Si un paquet échoue, on le rejoue ligne à ligne
        # pour isoler la ligne fautive.
        for start in range(0, len(pending), 100):
            chunk = pending[start:start + 100]
            ok_rows = chunk
            try:
                self.sb.table("market_prices").upsert(
                    [item[1] for item in chunk],
                    on_conflict="source_record_hash",
                ).execute()
            except Exception:
                ok_rows = []
                for item in chunk:
                    try:
                        self.sb.table("market_prices").upsert(
                            item[1],
                            on_conflict="source_record_hash",
                        ).execute()
                        ok_rows.append(item)
                    except Exception as exc:
                        errors += 1
                        self._mark_stage(item[0]["id"], "error", str(exc)[:500])
            for row, _payload, market_name, product_name, a_status, a_score in ok_rows:
                promoted += 1
                self._mark_stage(
                    row["id"],
                    "promoted",
                    None,
                    market_canonical=market_name,
                    product_canonical=product_name,
                    anomaly_status=a_status,
                    anomaly_score=a_score,
                )

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

        # Les relevés non publiés d'un passage précédent sont relus et retraités
        # à chaque passage (toutes les pages de la source) : ceux qui portent
        # encore un ancien run_id sont donc des variantes obsolètes (date ou unité
        # mal lues autrefois). On les marque pour garder une file lisible.
        if status in {"success", "partial"}:
            try:
                (
                    self.sb.table("market_price_staging")
                    .update({
                        "quality_status": "superseded",
                        "quality_reason": "ancien passage : relevé relu et retraité depuis",
                    })
                    .eq("source", self.source)
                    .neq("run_id", run_id)
                    .in_("quality_status", ["accepted", "error", "needs_review", "needs_mapping"])
                    .execute()
                )
            except Exception:
                pass

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
