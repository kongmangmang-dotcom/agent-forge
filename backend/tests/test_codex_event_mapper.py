from app.domain.enums import EventType, RunStatus
from app.providers.codex_event_mapper import map_codex_event


def test_turn_completed_maps_to_agent_completed():
    events = map_codex_event(
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 10, "output_tokens": 20},
        },
        "run_1",
        "agt_1",
    )
    assert len(events) == 1
    assert events[0].type == EventType.AGENT_COMPLETED
    assert events[0].status == RunStatus.COMPLETED
    assert events[0].metadata["input_tokens"] == "10"
    assert events[0].metadata["output_tokens"] == "20"


def test_turn_started_emits_nothing():
    assert map_codex_event({"type": "turn.started"}, "run_1", "agt_1") == []
