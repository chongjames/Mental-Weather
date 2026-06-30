"""Tests for timezone handling of time-of-day signals."""

from datetime import datetime, timedelta, timezone

import pytest

from mental_weather import metrics, parse
from mental_weather.parse import Export, Message


def _msg(dt_utc: datetime) -> Message:
    return Message(
        conversation_uuid="c",
        conversation_name="c",
        sender="human",
        text="hello there friend",
        created_at=dt_utc,
    )


def test_resolve_tz_offsets_and_utc():
    assert parse.resolve_tz("UTC") is timezone.utc
    assert parse.resolve_tz("").utcoffset(None) == timedelta(0)
    assert parse.resolve_tz("+08:00").utcoffset(None) == timedelta(hours=8)
    assert parse.resolve_tz("UTC+8").utcoffset(None) == timedelta(hours=8)
    assert parse.resolve_tz("-0530").utcoffset(None) == timedelta(hours=-5, minutes=-30)


def test_resolve_tz_rejects_garbage():
    with pytest.raises(ValueError):
        parse.resolve_tz("not/a/zone!!")
    with pytest.raises(ValueError):
        parse.resolve_tz("+99:00")


def test_with_timezone_shifts_late_night_out_of_window():
    # 02:00 UTC is "late night" in UTC, but 10:00 in UTC+8 (broad daylight).
    export = Export(messages=[_msg(datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc))])

    utc = metrics.compute(export.human_messages(), "utc")
    assert utc.late_night_ratio == 1.0  # 02:00 UTC is in 00:00-05:59

    parse.with_timezone(export, parse.resolve_tz("+08:00"))
    perth = metrics.compute(export.human_messages(), "perth")
    assert perth.late_night_ratio == 0.0  # 10:00 local is not late-night
    assert perth.hour_histogram == {10: 1}


def test_with_timezone_preserves_instant_ordering():
    # Conversion changes wall-clock, not the absolute instant.
    m = _msg(datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc))
    instant = m.created_at
    parse.with_timezone(Export(messages=[m]), parse.resolve_tz("+08:00"))
    assert m.created_at == instant  # same moment, different tzinfo


def test_cli_tz_changes_header_and_runs(tmp_path, capsys):
    from pathlib import Path

    from mental_weather import cli

    fixture = Path(__file__).parent / "fixtures" / "sample_export.json"
    out = tmp_path / "r.md"
    rc = cli.main([str(fixture), "--no-narrative", "--tz", "+08:00", "-o", str(out)])
    assert rc == 0
    assert "+08:00" in out.read_text(encoding="utf-8")


def test_cli_tz_rejects_bad_value(tmp_path):
    from pathlib import Path

    from mental_weather import cli

    fixture = Path(__file__).parent / "fixtures" / "sample_export.json"
    rc = cli.main([str(fixture), "--no-narrative", "--tz", "Mars/Olympus"])
    assert rc == 2
