"""前端后台监视器的关键契约。

这些断言不替代浏览器测试，但能防止以后整理单文件 HTML 时，悄悄删掉
流式监视、逐 Agent 思考开关、Enter 发送或 SSE 主链路。
"""
from pathlib import Path


INDEX = (Path(__file__).resolve().parents[2] / "index.html").read_text(encoding="utf-8")


def test_agent_monitor_has_live_detail_surfaces() -> None:
    assert 'id="agent-monitor"' in INDEX
    assert 'id="agent-run-list"' in INDEX
    assert 'id="agent-run-detail"' in INDEX
    assert "function monitorStart(" in INDEX
    assert "function monitorLive(" in INDEX
    assert "模型深度思考" in INDEX
    assert "输入／提示词" in INDEX
    assert "输出／结构化结果" in INDEX


def test_deepseek_thinking_is_configurable_per_agent() -> None:
    for agent in ("narrative", "planner", "director", "state", "memory"):
        assert f'id="set-think-{agent}"' in INDEX
        assert f"setAgentThinking('{agent}',this.checked)" in INDEX
    assert "thinkingEnabledForAgent(agentKind" in INDEX


def test_stream_writer_is_monitored_without_losing_sse_or_enter() -> None:
    assert "'/api/chat/stream'" in INDEX
    assert "agent:'narrative',title:'流式生成本回合场景正文'" in INDEX
    assert "monitorLive(monitorRunId,full,reasoning" in INDEX
    assert "if(e.key==='Enter'&&!e.shiftKey)" in INDEX
    assert "SETTINGS.stream" in INDEX


def test_action_options_have_tolerant_parser_and_repair_fallback() -> None:
    assert "function parseActionOptions(" in INDEX
    assert "function repairMissingActionOptions(" in INDEX
    assert 'id="set-optionrepair"' in INDEX
    assert "if(e.key==='Enter'&&!e.shiftKey)" in INDEX


def test_non_stream_reasoning_reaches_monitor() -> None:
    assert "reasoning_content:bj.reasoning_content||''" in INDEX
    assert "reasoning:pm.reasoning_content||pm.reasoning||''" in INDEX


def test_whole_turn_pipeline_exposes_major_stages() -> None:
    for stage in ("检索相关事实", "剧情规划", "组装上下文", "GM裁定", "场景写作", "状态审计", "保存与后台记忆"):
        assert f"'{stage}'" in INDEX


def test_structured_memory_is_wired_without_blocking_stream_writer() -> None:
    assert "function loreRecordLedger(" in INDEX
    assert "await loreRecordLedger(TURNS,reply,lastUser)" in INDEX
    assert "turn='+encodeURIComponent(TURNS)" in INDEX
    assert "memoryContext:{counts:lc,trace:" in INDEX
    assert "sceneContract:STORY_RUNTIME" in INDEX
    # 账本发生在正文完成后，不得取代或包住 SSE 主请求。
    assert INDEX.index("doFetchStream(msgs,narrTok") < INDEX.index("await loreRecordLedger(TURNS,reply,lastUser)")
