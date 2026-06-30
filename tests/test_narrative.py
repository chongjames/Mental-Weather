"""Tests for the narrative layer's offline stub path.

These exercise the *full* narrative path (payload assembly, generation, report
integration) without any API key or network, using the deterministic fake
backend. The live API path is intentionally not called here.
"""

from datetime import datetime, timezone
from pathlib import Path

from mental_weather import cli, metrics, narrative, parse, windows

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.json"
ANCHOR = datetime(2026, 6, 29, tzinfo=timezone.utc)


def _narrative_input():
    export = parse.load(FIXTURE)
    split = windows.split(export, anchor=ANCHOR)
    return narrative.NarrativeInput(
        baseline=split.baseline,
        recent=split.recent,
        deltas=metrics.deltas(split.baseline, split.recent),
        emerging_keywords=metrics.emerging_keywords(split.baseline, split.recent),
        samples=narrative.sample_snippets(split.recent_msgs),
    )


def test_fake_is_always_available():
    # The stub needs neither key nor SDK.
    assert narrative.is_available(fake=True) is True


def test_fake_is_available_via_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv(narrative.FAKE_ENV, "1")
    assert narrative.is_available() is True


def test_fake_generate_is_offline_and_data_driven():
    text = narrative.generate(_narrative_input(), fake=True)
    # Clearly labeled as a stub, never mistakable for a real read.
    assert "stub narrative" in text
    # It anchors to real signals from the fixture (sleep mentions jump 0 -> 300).
    assert "Sleep/tiredness mentions" in text
    # And surfaces emerging topics.
    assert "sleep" in text


def test_fake_generate_never_imports_sdk(monkeypatch):
    # Force any accidental `import anthropic` to explode so we prove the stub
    # path takes no live dependency.
    import builtins

    real_import = builtins.__import__

    def guard(name, *a, **k):
        if name == "anthropic":
            raise AssertionError("fake path must not import anthropic")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guard)
    text = narrative.generate(_narrative_input(), fake=True)
    assert text


def test_cli_fake_narrative_fills_weather_section(tmp_path, capsys):
    out = tmp_path / "report.md"
    rc = cli.main([str(FIXTURE), "--fake-narrative", "-o", str(out)])
    assert rc == 0
    md = out.read_text(encoding="utf-8")
    # The weather section is filled, not the "skipped" placeholder.
    assert "## The weather" in md
    assert "Narrative skipped" not in md
    assert "stub narrative" in md
