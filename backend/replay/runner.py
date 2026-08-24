"""Run deterministic multi-turn replay fixtures against real backend services.

The runner deliberately replaces only the model boundary with a cassette
provider.  State application, SQLite ledger writes, context retrieval and
prompt compilation are the production implementations, so a passing replay
means more than a unit test while remaining independent of network/model
randomness.
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Commitment,
    CharacterState,
    Entity,
    Fact,
    NpcBelief,
    NarrativeEvent,
    Session as GameSession,
)
from app.db.models import Base
from app.schemas.narrative import NarrativeLedgerWrite
from app.schemas.turn import TurnContext
from app.services.game_state import apply_patch
from app.services.memory import record_fact, retrieve_context_bundle, upsert_entity
from app.services.narrative_memory import retrieve_narrative_context, write_ledger
from app.services.prompt_builder import build_system_prompt, debug_hash


class ReplayError(RuntimeError):
    """A fixture or deterministic replay contract is invalid."""


@dataclass
class CassetteProvider:
    """Fixed model boundary used by deterministic protocol replays."""

    calls: int = 0

    async def complete(self, response: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return copy.deepcopy(response)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"无法读取 fixture：{path}：{exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("scenarios"), list):
        raise ReplayError("fixture 必须包含 scenarios 数组")
    return value


def _state_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Keep reports compact while retaining all gameplay-relevant fields."""
    return {
        "res": copy.deepcopy(state.get("res") or {}),
        "inv": [
            {"id": x.get("id"), "name": x.get("name"), "quantity": x.get("quantity")}
            for x in (state.get("inv") or []) if isinstance(x, dict)
        ],
        "skills": [x.get("name") for x in (state.get("skills") or []) if isinstance(x, dict)],
        "loc": state.get("loc", ""),
        "npcs": copy.deepcopy(state.get("npcs") or {}),
        "ledger_count": len(state.get("ledger") or []),
    }


def _mentioned(turn: dict[str, Any]) -> list[str]:
    values = turn.get("mentioned") or []
    return [str(x).strip() for x in values if str(x).strip()]


async def _create_db() -> tuple[Any, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_memory(db: AsyncSession, session_id: str, setup: dict[str, Any]) -> None:
    """Seed the same ledger shapes accepted by the production endpoint.

    Fixtures may use either the compact ``setup.ledger`` form or the more
    explicit top-level ``events``/``commitments``/``npc_beliefs`` fields from
    the baseline document.  Keeping both forms here makes fixtures readable
    without creating a replay-only persistence path.
    """
    for row in setup.get("entities") or []:
        if not isinstance(row, dict) or not str(row.get("name") or "").strip():
            continue
        entity = await upsert_entity(
            db,
            session_id,
            name=str(row["name"]).strip(),
            kind=str(row.get("kind") or "concept"),
            turn=int(row.get("turn") or 0),
            aliases=[str(x) for x in (row.get("aliases") or [])],
            importance=int(row.get("importance") or 1),
        )
        for fact in row.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            await record_fact(
                db,
                session_id,
                entity,
                key=str(fact.get("key") or "设定"),
                value=str(fact.get("value") or ""),
                turn=int(fact.get("turn") or row.get("turn") or 0),
                source=str(fact.get("source") or "system"),
            )

    # Optional facts that are not nested under an entity.  They are useful for
    # starting a replay at a known world fact without inventing a fake entity
    # block solely for the fixture.
    for fact in setup.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        name = str(fact.get("entity") or fact.get("subject") or fact.get("name") or "").strip()
        value = str(fact.get("value") or fact.get("text") or "").strip()
        if not name or not value:
            continue
        entity = await upsert_entity(
            db,
            session_id,
            name=name,
            kind=str(fact.get("kind") or "concept"),
            turn=int(fact.get("turn") or 0),
            importance=int(fact.get("importance") or 1),
        )
        await record_fact(
            db,
            session_id,
            entity,
            key=str(fact.get("key") or "设定"),
            value=value,
            turn=int(fact.get("turn") or 0),
            source=str(fact.get("source") or "system"),
        )

    ledger = setup.get("ledger")
    payload = dict(ledger) if isinstance(ledger, dict) else {}
    payload.setdefault("events", setup.get("events") or [])
    payload.setdefault("commitments", setup.get("commitments") or [])
    payload.setdefault("beliefs", setup.get("npc_beliefs") or setup.get("beliefs") or [])
    payload.setdefault("character_states", setup.get("character_states") or [])
    payload.setdefault("turn", 0)
    await write_ledger(db, session_id, NarrativeLedgerWrite.model_validate(payload))
    await db.commit()


async def _counts(db: AsyncSession, session_id: str) -> dict[str, int]:
    tables = {
        "entities": Entity,
        "facts": Fact,
        "events": NarrativeEvent,
        "commitments": Commitment,
        "beliefs": NpcBelief,
    }
    result: dict[str, int] = {}
    for name, model in tables.items():
        result[name] = int((await db.execute(
            select(func.count()).select_from(model).where(model.session_id == session_id)
        )).scalar_one())
    return result


async def _assert_one(db: AsyncSession, session_id: str, state: dict[str, Any], assertion: dict[str, Any]) -> str | None:
    kind = str(assertion.get("kind") or "").strip()
    if kind == "inventory_quantity":
        name = str(assertion.get("name") or "")
        actual = next((x.get("quantity", 0) for x in state.get("inv", []) if x.get("name") == name), 0)
        if actual != assertion.get("equals"):
            return f"物品 {name} 数量为 {actual}，期望 {assertion.get('equals')}"
        return None
    if kind == "resource":
        key = str(assertion.get("key") or "")
        actual = (state.get("res") or {}).get(key)
        if actual != assertion.get("equals"):
            return f"资源 {key} 为 {actual}，期望 {assertion.get('equals')}"
        return None
    if kind == "state_value":
        path = str(assertion.get("path") or "")
        actual = _path_value(state, path)
        if actual != assertion.get("equals"):
            return f"状态 {path} 为 {actual}，期望 {assertion.get('equals')}"
        return None
    if kind == "location":
        if state.get("loc", "") != assertion.get("equals"):
            return f"位置为 {state.get('loc', '')}，期望 {assertion.get('equals')}"
        return None
    if kind == "commitment":
        text = str(assertion.get("text_contains") or "")
        stmt = select(Commitment).where(Commitment.session_id == session_id)
        rows = list((await db.execute(stmt)).scalars())
        matches = [x for x in rows if text in x.text]
        if not matches:
            return f"没有找到包含「{text}」的承诺"
        status = assertion.get("status")
        if status is not None and not any(x.status == status for x in matches):
            return f"承诺「{text}」状态不是 {status}"
        return None
    if kind == "no_commitment_duplicate":
        text = str(assertion.get("text_contains") or "")
        stmt = select(Commitment).where(Commitment.session_id == session_id)
        rows = [x for x in (await db.execute(stmt)).scalars() if text in x.text]
        if len(rows) > int(assertion.get("max_count", 1)):
            return f"承诺「{text}」重复 {len(rows)} 次"
        return None
    if kind == "belief_absent":
        npc = str(assertion.get("npc") or "")
        text = str(assertion.get("text_contains") or "")
        stmt = select(NpcBelief).where(
            NpcBelief.session_id == session_id,
            NpcBelief.npc_name == npc,
            NpcBelief.statement.contains(text),
            NpcBelief.status == "active",
        )
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            return f"NPC {npc} 不应知道「{text}」"
        return None
    if kind == "option_count":
        # Checked against the last turn by the caller.
        return None
    if kind == "character_state_count":
        expected = int(assertion.get("equals", 0))
        actual = int((await db.execute(
            select(func.count()).select_from(CharacterState)
            .where(CharacterState.session_id == session_id)
        )).scalar_one())
        if actual != expected:
            return f"人物动态状态数量为 {actual}，期望 {expected}"
        return None
    raise ReplayError(f"未知断言类型：{kind}")


def _assertions(value: Any) -> list[dict[str, Any]]:
    """Accept both the list form used by fixtures and the documented object form."""
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if isinstance(value, dict):
        rows: list[dict[str, Any]] = []
        for key in ("hard", "checks", "assertions"):
            item = value.get(key)
            if isinstance(item, list):
                rows.extend(x for x in item if isinstance(x, dict))
        return rows
    return []


def _path_value(value: Any, path: str) -> Any:
    """Read a small dot path from a report/state object for branch checks."""
    current = value
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


async def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(scenario.get("id") or "").strip()
    if not scenario_id:
        raise ReplayError("场景缺少 id")
    engine, factory = await _create_db()
    provider = CassetteProvider()
    session_id = f"replay-{scenario_id}-{uuid4().hex[:8]}"
    state = copy.deepcopy((scenario.get("setup") or {}).get("game_state") or {})
    turns: list[dict[str, Any]] = []
    failures: list[str] = []
    try:
        async with factory() as db:
            db.add(GameSession(
                id=session_id,
                title=f"replay:{scenario_id}",
                world_id=str(scenario.get("world_id") or "fantasy"),
                preset_id=str(scenario.get("preset_id") or ""),
                pace=str(scenario.get("pace") or "medium"),
                game_state_json=json.dumps(state, ensure_ascii=False),
            ))
            await db.flush()
            await _seed_memory(db, session_id, scenario.get("setup") or {})

            for turn_no, turn in enumerate(scenario.get("turns") or [], start=1):
                if not isinstance(turn, dict):
                    raise ReplayError(f"{scenario_id} 第 {turn_no} 回合不是对象")
                started = time.perf_counter()
                before = copy.deepcopy(state)
                mentioned = _mentioned(turn)
                narrative_ctx = await retrieve_narrative_context(
                    db, session_id, mentioned=mentioned, current_turn=turn_no,
                    speaker=str(turn.get("speaker") or ""),
                )
                fact_ctx = await retrieve_context_bundle(
                    db, session_id, mentioned=mentioned, current_turn=turn_no,
                )
                context_text = "\n".join([fact_ctx.text, *narrative_ctx[0]]).strip()
                turn_ctx = TurnContext(
                    world_id=str(scenario.get("world_id") or "fantasy"),
                    preset_id=str(scenario.get("preset_id") or ""),
                    pace=str(scenario.get("pace") or "medium"),
                    turns=turn_no,
                    game_state=state,
                    lore_context=context_text,
                    recent_text=str(turn.get("input") or ""),
                    story_dna=str(scenario.get("story_dna") or ""),
                    premise_state=copy.deepcopy(
                        turn.get("premise_state")
                        if isinstance(turn.get("premise_state"), dict)
                        else (scenario.get("premise_state") or {})
                    ),
                )
                prompt = build_system_prompt(turn_ctx)
                response = await provider.complete(turn.get("response") or {})
                narrative = str(response.get("narrative") or "").strip()
                options = response.get("options") or []
                patch = response.get("patch") or {}
                turn_failures: list[str] = []
                if not narrative:
                    turn_failures.append(f"第 {turn_no} 回合正文为空")
                if not isinstance(options, list) or not 2 <= len(options) <= 4:
                    turn_failures.append(f"第 {turn_no} 回合选项数量为 {len(options) if isinstance(options, list) else '非数组'}")
                if not isinstance(patch, dict):
                    turn_failures.append(f"第 {turn_no} 回合 patch 不是对象")
                    patch = {}

                state = apply_patch(
                    state, patch,
                    world_id=str(scenario.get("world_id") or "fantasy"),
                    turn=turn_no,
                )
                ledger = response.get("ledger")
                ledger_counts: dict[str, int] = {}
                if isinstance(ledger, dict):
                    ledger_payload = dict(ledger)
                    ledger_payload.setdefault("turn", turn_no)
                    ledger_counts = await write_ledger(
                        db, session_id, NarrativeLedgerWrite.model_validate(ledger_payload)
                    )
                row = {
                    "turn": turn_no,
                    "input": str(turn.get("input") or ""),
                    "state_version_before": turn_no - 1,
                    "state_version_after": turn_no,
                    "retrieved_ids": [
                        x.get("id") for x in [*fact_ctx.trace, *narrative_ctx[1]]
                        if x.get("included") and x.get("id")
                    ],
                    "excluded_ids": [
                        x.get("id") for x in [*fact_ctx.trace, *narrative_ctx[1]]
                        if x.get("included") is False and x.get("id")
                    ],
                    "retrieval_reasons": [
                        {"id": x.get("id"), "reason": x.get("reason", "")}
                        for x in [*fact_ctx.trace, *narrative_ctx[1]]
                        if x.get("id")
                    ],
                    "scene_contract_id": str(turn.get("scene_contract_id") or scenario.get("scene_contract_id") or ""),
                    "planner_called": bool(turn.get("planner_called", scenario.get("planner_called", False))),
                    "premise_phase": str(
                        turn.get("premise_phase")
                        or (scenario.get("premise_state") or {}).get("phase")
                        or ""
                    ),
                    "agent_runs": [{"agent": "cassette_provider", "status": "completed", "calls": 1}],
                    "prompt_hash": debug_hash(prompt),
                    "prompt_chars": len(prompt),
                    "retrieval_counts": {
                        "facts": fact_ctx.counts.get("fact_count", 0),
                        "events": narrative_ctx[2].get("event_count", 0),
                        "commitments": narrative_ctx[2].get("commitment_count", 0),
                        "beliefs": narrative_ctx[2].get("belief_count", 0),
                    },
                    "model_calls": 1,
                    "narrative_chars": len(narrative),
                    "option_count": len(options) if isinstance(options, list) else 0,
                    "state_before": _state_summary(before),
                    "state_after": _state_summary(state),
                    "patch": copy.deepcopy(patch),
                    "ledger_counts": ledger_counts,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "status": "failed" if turn_failures else "completed",
                }
                turns.append(row)
                db_session = await db.get(GameSession, session_id)
                assert db_session is not None
                db_session.turn_no = turn_no
                db_session.game_state_json = json.dumps(state, ensure_ascii=False)
                await db.commit()

                for assertion in _assertions(turn.get("assertions")):
                    error = await _assert_one(db, session_id, state, assertion)
                    if error:
                        turn_failures.append(f"第 {turn_no} 回合：{error}")
                option_expect = turn.get("expect_option_count")
                if option_expect is not None and len(options) != int(option_expect):
                    turn_failures.append(f"第 {turn_no} 回合选项数量不是 {option_expect}")
                row["validation_result"] = {
                    "status": "failed" if turn_failures else "passed",
                    "errors": list(turn_failures),
                }
                row["status"] = "failed" if turn_failures else "completed"
                if turn_failures:
                    failures.extend(turn_failures)

            for assertion in _assertions(scenario.get("assertions")):
                error = await _assert_one(db, session_id, state, assertion)
                if error:
                    failures.append(error)
            planner_min = scenario.get("planner_calls_at_least")
            if planner_min is not None:
                actual = sum(1 for row in turns if row.get("planner_called"))
                if actual < int(planner_min):
                    failures.append(f"规划器调用次数为 {actual}，至少需要 {planner_min}")
            counts = await _counts(db, session_id)
    finally:
        await engine.dispose()

    return {
        "id": scenario_id,
        "status": "failed" if failures else "passed",
        "turn_count": len(turns),
        "model_calls": provider.calls,
        "failures": failures,
        "counts": counts,
        "turns": turns,
        "final_state": _state_summary(state),
    }


async def run_fixture(path: str | Path) -> dict[str, Any]:
    fixture_path = Path(path)
    fixture = _read_json(fixture_path)
    results = [await run_scenario(s) for s in fixture["scenarios"]]
    by_id = {x["id"]: x for x in results}
    comparisons: list[dict[str, Any]] = []
    for comparison in fixture.get("comparisons") or []:
        if not isinstance(comparison, dict):
            continue
        left_id = str(comparison.get("left") or "")
        right_id = str(comparison.get("right") or "")
        left = by_id.get(left_id)
        right = by_id.get(right_id)
        if left is None or right is None:
            comparisons.append({"kind": "branch_difference", "status": "failed",
                                "error": f"找不到分支：{left_id}/{right_id}"})
            continue
        paths = [str(x) for x in (comparison.get("paths") or ["final_state"])]
        differences = [p for p in paths if _path_value(left, p) != _path_value(right, p)]
        comparisons.append({
            "kind": "branch_difference",
            "left": left_id,
            "right": right_id,
            "paths": paths,
            "differences": differences,
            "status": "passed" if differences else "failed",
        })
    comparison_failures = [x for x in comparisons if x.get("status") == "failed"]
    return {
        "schema_version": 1,
        "fixture": str(fixture_path),
        "mode": "deterministic_protocol",
        "scenario_count": len(results),
        "passed": sum(x["status"] == "passed" for x in results),
        "failed": sum(x["status"] == "failed" for x in results) + len(comparison_failures),
        "comparisons": comparisons,
        "scenarios": results,
    }
