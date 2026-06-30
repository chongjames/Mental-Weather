from datetime import datetime, timezone
from pathlib import Path

from mental_weather import parse, report, windows

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.json"
ANCHOR = datetime(2026, 6, 29, tzinfo=timezone.utc)


def test_report_builds_without_narrative():
    export = parse.load(FIXTURE)
    split = windows.split(export, anchor=ANCHOR)
    md = report.build(export, split, narrative=None)
    assert "# Mental Weather Report" in md
    assert "Recent vs baseline" in md
    assert "Weekly trend" in md
    # Responsible-framing footer is always present.
    assert "not a clinical instrument" in md
    assert "does not diagnose" in md


def test_cli_smoke(tmp_path, capsys):
    from mental_weather import cli

    out = tmp_path / "report.md"
    rc = cli.main([str(FIXTURE), "--no-narrative", "-o", str(out)])
    assert rc == 0
    assert out.read_text(encoding="utf-8").startswith("# Mental Weather Report")
