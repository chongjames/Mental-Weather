"""Assemble the final markdown report from metrics (+ optional narrative)."""

from __future__ import annotations

from datetime import datetime

from .metrics import Delta, Metrics, deltas, emerging_keywords
from .parse import Export
from .windows import WindowSplit, weekly

FOOTER = (
    "_This is a reflection tool, not a clinical instrument. It reads patterns in "
    "how you write to Claude -- a thin, self-selected slice of your life -- and "
    "cannot see your sleep, behavior, health, or relationships. It does not "
    "diagnose anything. If something here resonates or worries you, talk to a "
    "person you trust or a professional._"
)


def _arrow(d: Delta) -> str:
    if d.change > 0:
        return "↑"
    if d.change < 0:
        return "↓"
    return "→"


def _fmt_pct(d: Delta) -> str:
    return "—" if d.pct_change is None else f"{d.pct_change:+.0f}%"


def _deltas_table(ds: list[Delta]) -> str:
    rows = [
        "| Signal | Baseline | Recent | Δ |",
        "| --- | ---: | ---: | :--- |",
    ]
    for d in ds:
        rows.append(
            f"| {d.field} | {d.baseline:g} | {d.recent:g} | {_arrow(d)} {_fmt_pct(d)} |"
        )
    return "\n".join(rows)


def _weekly_table(weeks: list[Metrics]) -> str:
    rows = [
        "| Week of | Msgs | Msgs/day | Median words | Late-night | Sleep/100 | Valence |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for w in weeks:
        rows.append(
            f"| {w.label} | {w.message_count} | {w.msgs_per_active_day:g} | "
            f"{w.median_words:g} | {w.late_night_ratio:g} | "
            f"{w.sleep_mentions_per_100:g} | {w.valence:g} |"
        )
    return "\n".join(rows)


def build(
    export: Export,
    split: WindowSplit,
    narrative: str | None = None,
    weeks: int = 12,
    generated_at: datetime | None = None,
    tz_label: str | None = None,
) -> str:
    ds = deltas(split.baseline, split.recent)
    emerging = emerging_keywords(split.baseline, split.recent)
    start, end = export.timespan()

    lines: list[str] = ["# Mental Weather Report", ""]
    if generated_at:
        lines.append(f"*Generated {generated_at.date().isoformat()}*  ")
    lines.append(
        f"*Source: {export.conversation_count()} conversations, "
        f"{len(export.human_messages())} of your messages"
        + (f", {start.date()} → {end.date()}" if start and end else "")
        + "*"
    )
    lines.append(
        f"*Time-of-day signals (late-night, hours) computed in **{tz_label or 'UTC'}**.*"
    )
    lines.append("")

    if narrative:
        lines += ["## The weather", "", narrative, ""]
    else:
        lines += [
            "## The weather",
            "",
            "_(Narrative skipped — no `ANTHROPIC_API_KEY` / `anthropic` SDK. "
            "Metrics below are the raw signals.)_",
            "",
        ]

    lines += [
        f"## Recent vs baseline",
        "",
        f"Recent window: **{split.recent.label}** "
        f"({split.recent.message_count} msgs). "
        f"Baseline: **{split.baseline.label}** "
        f"({split.baseline.message_count} msgs).",
        "",
        _deltas_table(ds),
        "",
    ]

    if emerging:
        lines += [
            "**New topics in the recent window** (absent from baseline): "
            + ", ".join(f"`{k}`" for k in emerging),
            "",
        ]

    lines += [
        "## Weekly trend",
        "",
        _weekly_table(weekly(export, weeks=weeks)),
        "",
        "---",
        "",
        FOOTER,
        "",
    ]
    return "\n".join(lines)
