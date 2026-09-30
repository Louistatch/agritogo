#!/usr/bin/env python3
"""Run CPC-Togo discovery, extraction, quality checks and Supabase promotion."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from app.ingestion.cpc import discover_cpc_source, extract_from_discovery


def _write_json(path: str, payload: object) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.getenv("CPC_URL", "https://www.cpc-togo.com/"))
    parser.add_argument("--report", default="artifacts/cpc-ingestion-report.json")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--settle-seconds", type=float, default=6.0)
    args = parser.parse_args()

    report = asyncio.run(
        discover_cpc_source(
            args.url,
            browser_ws_endpoint=os.getenv("CPC_BROWSER_WS_ENDPOINT") or None,
            settle_seconds=args.settle_seconds,
        )
    )
    observations, extraction = extract_from_discovery(report)

    accepted = [x for x in observations if x.quality_status == "accepted"]
    review = [x for x in observations if x.quality_status == "needs_review"]
    rejected = [x for x in observations if x.quality_status == "rejected"]

    summary = {
        "source": "SIM-CPC",
        "source_url": args.url,
        "discovery": report.to_dict(),
        "extraction": {
            k: v for k, v in extraction.items() if k != "raw_text"
        },
        "counts": {
            "observations": len(observations),
            "accepted": len(accepted),
            "needs_review": len(review),
            "rejected": len(rejected),
        },
        "sample": [x.to_dict() for x in observations[:25]],
        "persistence": {"mode": "dry_run" if args.dry_run else "supabase"},
    }

    has_supabase = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))
    if args.dry_run or not has_supabase:
        if not has_supabase and not args.dry_run:
            summary["persistence"]["warning"] = "Supabase secrets missing; switched to dry-run."
        _write_json(args.report, summary)
        print(json.dumps(summary["counts"], ensure_ascii=False))
        print(f"Report: {args.report}")
        return 0 if observations else 2

    from app.ingestion.pipeline import MarketIngestionPipeline

    pipeline = MarketIngestionPipeline(source="SIM-CPC")
    run_id = pipeline.start_run(args.url, report.to_dict())
    summary["persistence"]["run_id"] = run_id

    try:
        raw_id = pipeline.save_raw_payload(
            run_id=run_id,
            source_url=extraction.get("endpoint") or args.url,
            content_type=extraction.get("content_type") or "application/octet-stream",
            payload_text=extraction.get("raw_text") or "",
            extraction_mode=extraction.get("mode") or "unknown",
        )
        staged = pipeline.stage(run_id, raw_id, observations)
        promoted = pipeline.promote(run_id)
        pipeline.finish_run(
            run_id,
            staged=staged,
            promoted=promoted,
            endpoint=extraction.get("endpoint") or args.url,
            extraction_mode=extraction.get("mode") or "unknown",
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
                endpoint=extraction.get("endpoint") or args.url,
                extraction_mode=extraction.get("mode") or "unknown",
                error=str(exc)[:1000],
            )
        except Exception:
            pass
        _write_json(args.report, summary)
        raise

    _write_json(args.report, summary)
    print(json.dumps(summary["counts"], ensure_ascii=False))
    print(json.dumps(summary["persistence"], ensure_ascii=False))
    print(f"Report: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
