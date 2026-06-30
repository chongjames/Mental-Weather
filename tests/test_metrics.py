from datetime import datetime, timezone
from pathlib import Path

from mental_weather import metrics, parse, windows

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.json"
ANCHOR = datetime(2026, 6, 29, tzinfo=timezone.utc)


def load():
    return parse.load(FIXTURE)


def test_compute_ignores_assistant_messages():
    export = load()
    m = metrics.compute(export.messages, "all")
    # Only the 5 human messages counted.
    assert m.message_count == 5


def test_recent_window_signals():
    export = load()
    split = windows.split(export, recent_days=14, baseline_days=90, anchor=ANCHOR)
    recent = split.recent
    # Recent window = Jun 15-29: m5 (Jun 20, 3am) and m7 (Jun 21, 4:30am).
    assert recent.message_count == 2
    # Both posted between 00:00-05:59 UTC.
    assert recent.late_night_ratio == 1.0
    # "can't sleep", "exhausted", "awake" -> several sleep hits.
    assert recent.sleep_mentions >= 2
    # Grandiose words present in recent, absent in baseline.
    assert recent.grandiosity_per_100 > 0


def test_baseline_window_signals():
    export = load()
    split = windows.split(export, recent_days=14, baseline_days=90, anchor=ANCHOR)
    base = split.baseline
    # Baseline = Mar 16 - Jun 15: m1, m3 (Apr 10), m4 (May 2).
    assert base.message_count == 3
    # No late-night posts in baseline.
    assert base.late_night_ratio == 0.0
    # Positive valence baseline (calm/good/hopeful/grateful...).
    assert base.valence > 0


def test_deltas_capture_shift():
    export = load()
    split = windows.split(export, recent_days=14, baseline_days=90, anchor=ANCHOR)
    ds = {d.field: d for d in metrics.deltas(split.baseline, split.recent)}
    # Late-night rose, valence fell.
    assert ds["late_night_ratio"].change > 0
    assert ds["valence"].change < 0


def test_emerging_keywords_recent_only():
    export = load()
    split = windows.split(export, recent_days=14, baseline_days=90, anchor=ANCHOR)
    emerging = metrics.emerging_keywords(split.baseline, split.recent)
    # "sleep" is prominent in recent ("can't sleep") and absent from baseline
    # ("slept" tokenizes differently), so it should surface as emerging.
    assert "sleep" in emerging
    # By contract, nothing emerging may also be a baseline top keyword.
    baseline_kw = {k for k, _ in split.baseline.top_keywords}
    assert not (set(emerging) & baseline_kw)


def test_empty_window_is_safe():
    m = metrics.compute([], "empty")
    assert m.message_count == 0
    assert m.valence == 0.0
    assert m.top_keywords == []
