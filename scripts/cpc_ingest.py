#!/usr/bin/env python3
"""Run resilient CPC-Togo market-data ingestion.

Production strategy:
1. Reuse a known-good endpoint with ETag/Last-Modified validators.
2. If it fails, launch browser discovery and learn the new feed.
3. Persist raw payload, normalize, quality-check and promote safe records.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.ingestion.cpc import discover_cpc_source, extract_from_discovery


# SIM-CPC publie des prix au kilogramme. Le chemin « endpoint en cache » n'a pas la
# page sous les yeux pour le lire : sans indication, 711 relevés sortaient avec une
# unité inconnue (« unknown_unit »).
CPC_UNIT_HINT = "kg"


def _write_json(path: str, payload: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _quality_counts(observations: list[Any]) -> dict[str, int]:
    return {
        "observations": len(observations),
        "accepted": sum(
            item.quality_status == "accepted"
            for item in observations
        ),
        "needs_review": sum(
            item.quality_status == "needs_review"
            for item in observations
        ),
        "rejected": sum(
            item.quality_status == "rejected"
            for item in observations
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=os.getenv(
            "CPC_URL",
            "https://www.cpc-togo.com/prixproduit",
        ),
    )
    parser.add_argument(
        "--report",
        default="artifacts/cpc-ingestion-report.json",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-discovery", action="store_true")
    parser.add_argument("--settle-seconds", type=float, default=6.0)
    args = parser.parse_args()

    has_supabase = bool(
        os.getenv("SUPABASE_URL")
        and os.getenv("SUPABASE_SERVICE_KEY")
    )

    # Sans secrets Supabase, une exécution NON test ne peut rien enregistrer. Elle
    # réussissait pourtant (bonus : le scraping trouvait des prix), si bien que le
    # workflow planifié restait vert pendant que la base ne recevait rien. On
    # échoue d'emblée et bruyamment ; seul --dry-run (PR) tourne sans secrets.
    if not has_supabase and not args.dry_run:
        print(
            "ERREUR : SUPABASE_URL et/ou SUPABASE_SERVICE_KEY manquants. "
            "Rien ne serait enregistré. Définissez ces secrets du dépôt "
            "(Settings > Secrets and variables > Actions) ou utilisez --dry-run.",
            file=sys.stderr,
        )
        return 3

    registry = None
    observations = []
    extraction: dict[str, Any] = {}
    discovery_dict: dict[str, Any] = {}
    acquisition_attempts: list[dict[str, Any]] = []

    # Fast path: the feed discovered on an earlier run.
    if has_supabase and not args.dry_run and not args.force_discovery:
        from app.ingestion.endpoints import MarketEndpointRegistry

        registry = MarketEndpointRegistry(source="SIM-CPC")
        for endpoint in registry.best(limit=5):
            try:
                observations, extraction = registry.collect(endpoint, unit_hint=CPC_UNIT_HINT)
                acquisition_attempts.append({
                    "mode": "cached_endpoint",
                    "endpoint": endpoint.get("url"),
                    "status": extraction.get("status"),
                    "observations": len(observations),
                    "not_modified": extraction.get(
                        "not_modified",
                        False,
                    ),
                })
                if extraction.get("not_modified"):
                    summary = {
                        "source": "SIM-CPC",
                        "source_url": args.url,
                        "acquisition": acquisition_attempts,
                        "counts": _quality_counts([]),
                        "persistence": {
                            "mode": "supabase",
                            "status": "not_modified",
                        },
                    }
                    _write_json(args.report, summary)
                    print(json.dumps(summary, ensure_ascii=False))
                    return 0
                if observations:
                    discovery_dict = {
                        "mode": "cached_endpoint",
                        "endpoint": endpoint.get("url"),
                    }
                    break
            except Exception as exc:
                acquisition_attempts.append({
                    "mode": "cached_endpoint",
                    "endpoint": endpoint.get("url"),
                    "error": str(exc)[:500],
                })

    # Recovery path: rediscover the front-end data contract.
    if not observations:
        report = asyncio.run(
            discover_cpc_source(
                args.url,
                browser_ws_endpoint=(
                    os.getenv("CPC_BROWSER_WS_ENDPOINT") or None
                ),
                settle_seconds=args.settle_seconds,
            ),
        )
        discovery_dict = report.to_dict()
        observations, extraction = extract_from_discovery(report)
        acquisition_attempts.append({
            "mode": extraction.get("mode") or "browser_discovery",
            "endpoint": extraction.get("endpoint"),
            "observations": len(observations),
            "candidates": len(report.candidates),
            "visited_pages": len(report.visited_pages),
            "script_endpoint_hints": len(
                report.script_endpoint_hints,
            ),
        })

        if has_supabase and not args.dry_run:
            if registry is None:
                from app.ingestion.endpoints import (
                    MarketEndpointRegistry,
                )

                registry = MarketEndpointRegistry(source="SIM-CPC")
            registry.remember_candidates(report.candidates)

    summary = {
        "source": "SIM-CPC",
        "source_url": args.url,
        "acquisition": acquisition_attempts,
        "discovery": discovery_dict,
        "extraction": {
            key: value
            for key, value in extraction.items()
            if key != "raw_text"
        },
        "counts": _quality_counts(observations),
        "sample": [
            item.to_dict()
            for item in observations[:25]
        ],
        "persistence": {
            "mode": (
                "dry_run"
                if args.dry_run or not has_supabase
                else "supabase"
            ),
        },
    }

    if args.dry_run or not has_supabase:
        _write_json(args.report, summary)
        print(json.dumps(summary["counts"], ensure_ascii=False))
        print(f"Report: {args.report}")
        return 0 if observations else 2

    from app.ingestion.pipeline import MarketIngestionPipeline

    pipeline = MarketIngestionPipeline(source="SIM-CPC")
    run_id = pipeline.start_run(
        args.url,
        discovery_dict,
    )
    summary["persistence"]["run_id"] = run_id

    try:
        raw_id = pipeline.save_raw_payload(
            run_id=run_id,
            source_url=(
                extraction.get("endpoint")
                or args.url
            ),
            content_type=(
                extraction.get("content_type")
                or "application/octet-stream"
            ),
            payload_text=extraction.get("raw_text") or "",
            extraction_mode=(
                extraction.get("mode") or "unknown"
            ),
        )
        staged = pipeline.stage(
            run_id,
            raw_id,
            observations,
        )
        promoted = pipeline.promote(run_id)
        pipeline.finish_run(
            run_id,
            staged=staged,
            promoted=promoted,
            endpoint=(
                extraction.get("endpoint")
                or args.url
            ),
            extraction_mode=(
                extraction.get("mode") or "unknown"
            ),
        )
        summary["persistence"].update({
            "raw_payload_id": raw_id,
            "staged": staged,
            "promoted": promoted,
        })
    except Exception as exc:
        summary["persistence"]["error"] = str(exc)
        try:
            pipeline.finish_run(
                run_id,
                staged={"staged": 0},
                promoted={"promoted": 0, "errors": 1},
                endpoint=(
                    extraction.get("endpoint")
                    or args.url
                ),
                extraction_mode=(
                    extraction.get("mode") or "unknown"
                ),
                error=str(exc)[:1000],
            )
        except Exception:
            pass
        _write_json(args.report, summary)
        raise

    _write_json(args.report, summary)
    print(json.dumps(summary["counts"], ensure_ascii=False))
    print(
        json.dumps(
            summary["persistence"],
            ensure_ascii=False,
        ),
    )
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
