"""Slice an export's timeline into windows for comparison.

The default report compares a *recent* window against a *baseline* window
immediately preceding it -- "the last 14 days vs the 90 before that". We also
expose a rolling weekly breakdown so trends can be read directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .metrics import Metrics, compute
from .parse import Export, Message


@dataclass
class WindowSplit:
    baseline: Metrics
    recent: Metrics
    baseline_msgs: list[Message]
    recent_msgs: list[Message]


def _anchor(export: Export, anchor: datetime | None) -> datetime:
    if anchor is not None:
        return anchor
    _, end = export.timespan()
    return end or datetime.now(timezone.utc)


def split(
    export: Export,
    recent_days: int = 14,
    baseline_days: int = 90,
    anchor: datetime | None = None,
) -> WindowSplit:
    """Split into recent vs baseline windows ending at ``anchor``."""
    end = _anchor(export, anchor)
    recent_start = end - timedelta(days=recent_days)
    baseline_start = recent_start - timedelta(days=baseline_days)

    recent_msgs, baseline_msgs = [], []
    for msg in export.human_messages():
        if msg.created_at is None:
            continue
        if recent_start < msg.created_at <= end:
            recent_msgs.append(msg)
        elif baseline_start < msg.created_at <= recent_start:
            baseline_msgs.append(msg)

    return WindowSplit(
        baseline=compute(baseline_msgs, f"baseline ({baseline_days}d)"),
        recent=compute(recent_msgs, f"recent ({recent_days}d)"),
        baseline_msgs=baseline_msgs,
        recent_msgs=recent_msgs,
    )


def weekly(export: Export, weeks: int = 12, anchor: datetime | None = None) -> list[Metrics]:
    """Return per-week metrics for the last ``weeks`` weeks, oldest first."""
    end = _anchor(export, anchor)
    out: list[Metrics] = []
    for i in range(weeks - 1, -1, -1):
        w_end = end - timedelta(weeks=i)
        w_start = w_end - timedelta(weeks=1)
        msgs = [
            m
            for m in export.human_messages()
            if m.created_at and w_start < m.created_at <= w_end
        ]
        label = w_start.date().isoformat()
        out.append(compute(msgs, label))
    return out
