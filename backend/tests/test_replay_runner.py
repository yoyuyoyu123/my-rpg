"""Deterministic protocol replay smoke tests."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from replay.runner import run_fixture


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "research" / "regression" / "fixtures" / "replay_baseline.json"


def test_seed_replay_passes_all_scenarios() -> None:
    report = asyncio.run(run_fixture(FIXTURE))
    assert report["scenario_count"] == 10
    assert report["passed"] == 10
    assert report["failed"] == 0
    assert report["comparisons"][0]["status"] == "passed"

    by_id = {row["id"]: row for row in report["scenarios"]}
    assert by_id["commitment_recall_5_turns"]["counts"]["commitments"] == 1
    assert by_id["npc_knowledge_boundary_3_turns"]["counts"]["beliefs"] == 1
    assert by_id["state_transaction_4_turns"]["final_state"]["res"]["coins"] == 80
    assert by_id["transmigration_chain_5_turns"]["final_state"]["loc"] == "学院门口"
    assert by_id["xianxia_growth_4_turns"]["final_state"]["res"]["灵石"] == 2


def test_seed_replay_is_protocol_stable() -> None:
    first = asyncio.run(run_fixture(FIXTURE))
    second = asyncio.run(run_fixture(FIXTURE))

    def stable(report: dict) -> dict:
        data = json.loads(json.dumps(report, ensure_ascii=False))
        for scenario in data["scenarios"]:
            for turn in scenario["turns"]:
                turn.pop("duration_ms", None)
        return data

    assert stable(first) == stable(second)
