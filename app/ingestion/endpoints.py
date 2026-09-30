"""Persistent fast-path for discovered public market-data endpoints."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import requests

from app.database import get_db
from app.ingestion.cpc import EndpointCandidate, MarketObservation, normalize_payload


class MarketEndpointRegistry:
    """Reuse known-good endpoints and rediscover only when needed."""

    def __init__(self, source: str = "SIM-CPC") -> None:
        self.sb = get_db()
        self.source = source

    def best(self, limit: int = 5) -> list[dict[str, Any]]:
        try:
            return (
                self.sb.table("market_source_endpoints")
                .select("*")
                .eq("source", self.source)
                .eq("active", True)
                .order("consecutive_failures")
                .order("discovery_score", desc=True)
                .order("last_success_at", desc=True)
                .limit(limit)
                .execute()
                .data
                or []
            )
        except Exception:
            return []

    def remember_candidates(
        self,
        candidates: list[EndpointCandidate],
    ) -> None:
        rows = []
        for candidate in candidates:
            if candidate.score < 8:
                continue
            rows.append({
                "source": self.source,
                "url": candidate.url,
                "method": candidate.method.upper(),
                "request_post_data": candidate.request_post_data,
                "content_type": candidate.content_type,
                "discovered_via": candidate.discovered_via,
                "discovery_score": candidate.score,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
        for start in range(0, len(rows), 100):
            chunk = rows[start:start + 100]
            if chunk:
                self.sb.table("market_source_endpoints").upsert(
                    chunk,
                    on_conflict="source,method,url",
                ).execute()

    def collect(
        self,
        endpoint: dict[str, Any],
        unit_hint: str | None = None,
    ) -> tuple[list[MarketObservation], dict[str, Any]]:
        headers = {
            "User-Agent": (
                "AgriTogoData/1.0 "
                "(market-intelligence; respectful conditional polling)"
            ),
            "Accept": (
                "application/json,text/csv,text/plain,text/html;"
                "q=0.9,*/*;q=0.5"
            ),
            "Referer": "https://www.cpc-togo.com/prixproduit",
        }
        etag = endpoint.get("etag")
        last_modified = endpoint.get("last_modified")
        if etag:
            headers["If-None-Match"] = etag
        elif last_modified and endpoint.get("method", "GET").upper() == "GET":
            headers["If-Modified-Since"] = last_modified

        method = (endpoint.get("method") or "GET").upper()
        kwargs: dict[str, Any] = {
            "headers": headers,
            "timeout": 30,
            "allow_redirects": True,
        }
        post_data = endpoint.get("request_post_data")
        if method == "POST" and post_data:
            stripped = str(post_data).lstrip()
            if stripped.startswith(("{", "[")):
                try:
                    import json

                    kwargs["json"] = json.loads(post_data)
                except Exception:
                    kwargs["data"] = post_data
            else:
                kwargs["data"] = post_data

        checked_at = datetime.now(timezone.utc).isoformat()
        response = requests.request(
            method,
            endpoint["url"],
            **kwargs,
        )

        if response.status_code == 304:
            self._mark_success(
                endpoint,
                checked_at,
                etag=response.headers.get("ETag") or etag,
                last_modified=(
                    response.headers.get("Last-Modified")
                    or last_modified
                ),
            )
            return [], {
                "mode": "cached_endpoint",
                "endpoint": endpoint["url"],
                "not_modified": True,
                "status": 304,
                "content_type": endpoint.get("content_type") or "",
                "raw_text": "",
            }

        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        observations = normalize_payload(
            response.text,
            content_type,
            response.url,
            source=self.source,
            unit_hint=unit_hint,
        )

        if not observations:
            self._mark_failure(
                endpoint,
                checked_at,
                "response contained no recognizable market observations",
            )
            return [], {
                "mode": "cached_endpoint",
                "endpoint": response.url,
                "not_modified": False,
                "status": response.status_code,
                "content_type": content_type,
                "raw_text": response.text[:500_000],
                "empty": True,
            }

        self._mark_success(
            endpoint,
            checked_at,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
        return observations, {
            "mode": "cached_endpoint",
            "endpoint": response.url,
            "not_modified": False,
            "status": response.status_code,
            "content_type": content_type,
            "raw_text": response.text[:500_000],
        }

    def deactivate_if_stale(
        self,
        endpoint: dict[str, Any],
        threshold: int = 5,
    ) -> None:
        failures = int(endpoint.get("consecutive_failures") or 0)
        if failures + 1 < threshold:
            return
        try:
            self.sb.table("market_source_endpoints").update({
                "active": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", endpoint["id"]).execute()
        except Exception:
            pass

    def _mark_success(
        self,
        endpoint: dict[str, Any],
        checked_at: str,
        *,
        etag: str | None,
        last_modified: str | None,
    ) -> None:
        try:
            self.sb.table("market_source_endpoints").update({
                "success_count": int(endpoint.get("success_count") or 0) + 1,
                "consecutive_failures": 0,
                "last_checked_at": checked_at,
                "last_success_at": checked_at,
                "last_error": None,
                "etag": etag,
                "last_modified": last_modified,
                "updated_at": checked_at,
            }).eq("id", endpoint["id"]).execute()
        except Exception:
            pass

    def _mark_failure(
        self,
        endpoint: dict[str, Any],
        checked_at: str,
        error: str,
    ) -> None:
        failures = int(endpoint.get("consecutive_failures") or 0) + 1
        try:
            self.sb.table("market_source_endpoints").update({
                "failure_count": int(endpoint.get("failure_count") or 0) + 1,
                "consecutive_failures": failures,
                "last_checked_at": checked_at,
                "last_error": error[:1000],
                "updated_at": checked_at,
                "active": failures < 5,
            }).eq("id", endpoint["id"]).execute()
        except Exception:
            pass
