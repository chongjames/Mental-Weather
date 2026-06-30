from datetime import datetime, timezone
from pathlib import Path

from mental_weather import parse

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.json"


def load():
    return parse.load(FIXTURE)


def test_loads_all_messages_with_text():
    export = load()
    # 7 messages in fixture, all have text -> 7 parsed.
    assert len(export.messages) == 7


def test_human_vs_assistant_normalization():
    export = load()
    humans = export.human_messages()
    # m1, m3(user), m4, m5(role:human), m7 -> 5 human messages.
    assert len(humans) == 5
    # "user" and "role" variants both map to human.
    assert all(m.sender == "human" for m in humans)


def test_content_blocks_are_extracted():
    export = load()
    m3 = next(m for m in export.messages if "patience" in m.text)
    assert m3.text == "Just patience. I enjoy the slow days."


def test_project_extraction_dict_and_string_and_none():
    export = load()
    by_conv = {m.conversation_uuid: m.project for m in export.messages}
    assert by_conv["conv-baseline-1"] == "Trading"
    assert by_conv["conv-baseline-2"] == "Personal"
    assert by_conv["conv-recent-1"] is None


def test_timestamps_parsed_to_utc():
    export = load()
    m1 = next(m for m in export.messages if m.conversation_uuid == "conv-baseline-1")
    assert m1.created_at == datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)


def test_messages_sorted_chronologically():
    export = load()
    stamps = [m.created_at for m in export.messages]
    assert stamps == sorted(stamps)


def test_timestamp_z_suffix_and_offset_equivalent():
    assert parse.parse_timestamp("2026-06-20T03:00:00Z") == parse.parse_timestamp(
        "2026-06-20T03:00:00+00:00"
    )


def test_malformed_timestamp_returns_none():
    assert parse.parse_timestamp("not-a-date") is None
    assert parse.parse_timestamp("") is None
    assert parse.parse_timestamp(None) is None


def test_handles_dict_wrapped_export():
    export = parse.from_conversations(
        {"conversations": [
            {"uuid": "c", "name": "n", "chat_messages": [
                {"sender": "human", "text": "hi", "created_at": "2026-01-01T00:00:00Z"}
            ]}
        ]}
    )
    assert len(export.human_messages()) == 1
