#!/usr/bin/env python3
"""Discover CPC-Togo's browser data feed without hard-coding an endpoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.ingestion.cpc import discover_cpc_source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.getenv("CPC_URL", "https://www.cpc-togo.com/"))
    parser.add_argument("--output", default="artifacts/cpc-discovery.json")
    parser.add_argument("--settle-seconds", type=float, default=6.0)
    args = parser.parse_args()

    report = asyncio.run(
        discover_cpc_source(
            args.url,
            browser_ws_endpoint=os.getenv("CPC_BROWSER_WS_ENDPOINT") or None,
            settle_seconds=args.settle_seconds,
        )
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"CPC discovery: {len(report.candidates)} endpoint candidates, {len(report.dom_tables)} DOM tables")
    for candidate in report.candidates[:8]:
        print(f"  score={candidate.score:02d} {candidate.method} {candidate.url} [{candidate.content_type}]")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
