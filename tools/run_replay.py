#!/usr/bin/env python3
"""CLI for deterministic protocol replay fixtures.

Example:
    backend/.venv/Scripts/python.exe tools/run_replay.py \
        --fixture research/regression/fixtures/replay_baseline.json \
        --out research/regression/out/replay_latest.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from replay.runner import ReplayError, run_fixture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic narrative protocol replays")
    parser.add_argument("--fixture", required=True, help="fixture JSON path")
    parser.add_argument("--out", help="write the full report to this JSON path")
    args = parser.parse_args()
    try:
        report = asyncio.run(run_fixture(args.fixture))
    except ReplayError as exc:
        print(f"replay error: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        output = (ROOT / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(f"replay: {report['passed']}/{report['scenario_count']} scenarios passed")
    if report["failed"]:
        for scenario in report["scenarios"]:
            for failure in scenario["failures"]:
                print(f"- {scenario['id']}: {failure}", file=sys.stderr)
        for comparison in report.get("comparisons", []):
            if comparison.get("status") == "failed":
                print(f"- branch comparison: {comparison.get('error') or comparison}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
