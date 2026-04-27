"""Unit tests for brainstorm discussion mode."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def make_stage1(models):
    return [{"model": m, "response": f"Initial answer from {m}", "error": None} for m in models]


def make_settings(max_cycles=4, council_temp=0.5, chairman_temp=0.4):
    s = MagicMock()
    s.brainstorm_max_cycles = max_cycles
    s.council_temperature = council_temp
    s.chairman_temperature = chairman_temp
    return s


async def collect_events(gen):
    events = []
    async for item in gen:
        events.append(item)
    return events


@pytest.mark.asyncio
async def test_early_exit_on_consensus():
    """When chairman signals CONSENSUS: YES after cycle 2, discussion stops early."""
    models = ["modelA", "modelB"]
    stage1 = make_stage1(models)

    def mock_query(model, messages, **kwargs):
        if model == "chairman":
            return {"content": "All agreed.\nCONSENSUS: YES", "error": False}
        return {"content": f"Turn from {model}", "error": False}

    with patch("backend.council.get_settings", return_value=make_settings(max_cycles=4)):
        with patch("backend.council.query_model", side_effect=mock_query):
            with patch("backend.council.get_chairman_model", return_value="chairman"):
                from backend.council import brainstorm_discussion
                events = await collect_events(brainstorm_discussion("topic", stage1))

    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["consensus_reached"] is True
    assert done_events[0]["reason"] == "consensus"
    assert done_events[0]["final_cycle"] == 2

    # Should not have cycle 3 or 4 events
    cycle_starts = [e for e in events if e["type"] == "cycle_start"]
    assert all(e["cycle"] <= 2 for e in cycle_starts)


@pytest.mark.asyncio
async def test_runs_to_max_cycles_when_no_consensus():
    """With CONSENSUS: NO every time, runs all cycles and stops at max_cycles."""
    models = ["modelA", "modelB"]
    stage1 = make_stage1(models)

    def mock_query(model, messages, **kwargs):
        if model == "chairman":
            return {"content": "Still disagreeing.\nCONSENSUS: NO", "error": False}
        return {"content": f"Turn from {model}", "error": False}

    with patch("backend.council.get_settings", return_value=make_settings(max_cycles=4)):
        with patch("backend.council.query_model", side_effect=mock_query):
            with patch("backend.council.get_chairman_model", return_value="chairman"):
                from backend.council import brainstorm_discussion
                events = await collect_events(brainstorm_discussion("topic", stage1))

    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assert done_events[0]["consensus_reached"] is False
    assert done_events[0]["reason"] == "max_cycles"
    assert done_events[0]["final_cycle"] == 4


@pytest.mark.asyncio
async def test_turn_count_is_models_times_cycles():
    """With 3 models and max_cycles=2, exactly 6 turn_complete events before consensus check."""
    models = ["A", "B", "C"]
    stage1 = make_stage1(models)

    def mock_query(model, messages, **kwargs):
        if model == "chairman":
            return {"content": "CONSENSUS: NO", "error": False}
        return {"content": f"Turn from {model}", "error": False}

    with patch("backend.council.get_settings", return_value=make_settings(max_cycles=2)):
        with patch("backend.council.query_model", side_effect=mock_query):
            with patch("backend.council.get_chairman_model", return_value="chairman"):
                from backend.council import brainstorm_discussion
                events = await collect_events(brainstorm_discussion("topic", stage1))

    turn_events = [e for e in events if e["type"] == "turn_complete"]
    assert len(turn_events) == 6


@pytest.mark.asyncio
async def test_summary_every_two_cycles():
    """With max_cycles=4 and no consensus, summaries appear at cycles 2 and 4 only."""
    models = ["A", "B"]
    stage1 = make_stage1(models)

    def mock_query(model, messages, **kwargs):
        if model == "chairman":
            return {"content": "Still disagreeing.\nCONSENSUS: NO", "error": False}
        return {"content": "Turn content", "error": False}

    with patch("backend.council.get_settings", return_value=make_settings(max_cycles=4)):
        with patch("backend.council.query_model", side_effect=mock_query):
            with patch("backend.council.get_chairman_model", return_value="chairman"):
                from backend.council import brainstorm_discussion
                events = await collect_events(brainstorm_discussion("topic", stage1))

    summary_events = [e for e in events if e["type"] == "summary_complete"]
    summary_cycles = [e["cycle"] for e in summary_events]
    assert summary_cycles == [2, 4]


@pytest.mark.asyncio
async def test_turn_prompt_includes_prior_turn_history():
    """After model A speaks, the prompt passed to model B contains A's turn content."""
    models = ["modelA", "modelB"]
    stage1 = make_stage1(models)
    captured_prompts = {}

    async def mock_query(model, messages, **kwargs):
        if model == "chairman":
            return {"content": "CONSENSUS: NO", "error": False}
        captured_prompts[model] = messages[0]["content"]
        return {"content": f"Response from {model}", "error": False}

    with patch("backend.council.get_settings", return_value=make_settings(max_cycles=2)):
        with patch("backend.council.query_model", side_effect=mock_query):
            with patch("backend.council.get_chairman_model", return_value="chairman"):
                from backend.council import brainstorm_discussion
                await collect_events(brainstorm_discussion("topic", stage1))

    assert "modelB" in captured_prompts
    assert "Response from modelA" in captured_prompts["modelB"]


@pytest.mark.asyncio
async def test_consensus_parsing_case_insensitive():
    """'consensus: yes' (lowercase) is detected as consensus."""
    models = ["A"]
    stage1 = make_stage1(models)

    def mock_query(model, messages, **kwargs):
        if model == "chairman":
            return {"content": "All good!\nconsensus: yes", "error": False}
        return {"content": "Turn", "error": False}

    with patch("backend.council.get_settings", return_value=make_settings(max_cycles=2)):
        with patch("backend.council.query_model", side_effect=mock_query):
            with patch("backend.council.get_chairman_model", return_value="chairman"):
                from backend.council import brainstorm_discussion
                events = await collect_events(brainstorm_discussion("topic", stage1))

    done = next(e for e in events if e["type"] == "done")
    assert done["consensus_reached"] is True


def test_brainstorm_max_cycles_default():
    """Settings default for brainstorm_max_cycles is 4."""
    from backend.settings import Settings
    assert Settings().brainstorm_max_cycles == 4
