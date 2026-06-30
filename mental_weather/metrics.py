"""Deterministic, offline metrics over a set of messages.

Everything here runs locally with no network and no LLM. The numbers are
deliberately *blunt* -- they are signals to look at, not measurements of a
person. Each metric is named for what it literally counts, not for what it
might mean.

The interpretation (turning "late-night ratio is up 0.18" into a sentence)
is left to :mod:`mental_weather.narrative` or to you.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Sequence

from .parse import Message

# --------------------------------------------------------------------------- #
# Small embedded lexicons. These are crude on purpose and labeled as such in
# any output. They are not a sentiment model.
# --------------------------------------------------------------------------- #

_WORD_RE = re.compile(r"[a-zA-Z']+")

SELF_REF = {"i", "i'm", "im", "i've", "ive", "i'd", "i'll", "me", "my", "mine", "myself"}

SLEEP_RE = re.compile(
    r"\b(sleep|asleep|insomnia|tired|exhausted|awake|can't sleep|cant sleep|"
    r"up all night|3am|4am|5am|wired|restless|nap|fatigue)\b",
    re.IGNORECASE,
)

POSITIVE_WORDS = {
    "good", "great", "love", "loving", "excited", "happy", "amazing", "awesome",
    "wonderful", "grateful", "calm", "hopeful", "proud", "win", "winning",
    "progress", "better", "best", "enjoy", "enjoying", "fun", "glad", "thanks",
    "thank", "brilliant", "perfect", "incredible", "optimistic",
}
NEGATIVE_WORDS = {
    "bad", "hate", "angry", "anxious", "anxiety", "scared", "afraid", "worried",
    "worry", "sad", "depressed", "tired", "exhausted", "stuck", "fail", "failing",
    "failed", "frustrated", "frustrating", "stressed", "stress", "overwhelmed",
    "hopeless", "alone", "lonely", "wrong", "broken", "fight", "fighting",
    "conflict", "problem", "panic", "dread",
}

GRANDIOSE_WORDS = {
    "revolutionary", "genius", "billion", "millions", "empire", "destiny",
    "unstoppable", "best ever", "changing the world", "the best", "no one else",
    "everyone", "always", "never", "massive", "huge", "epic",
}

# Common English stopwords for fixation/keyword extraction.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "to", "of", "in",
    "on", "for", "with", "as", "at", "by", "from", "is", "are", "was", "were",
    "be", "been", "being", "it", "its", "this", "that", "these", "those", "i",
    "im", "i'm", "you", "your", "we", "they", "he", "she", "them", "his", "her",
    "my", "me", "mine", "our", "us", "do", "does", "did", "doing", "have", "has",
    "had", "not", "no", "yes", "can", "could", "would", "should", "will", "just",
    "like", "get", "got", "go", "going", "want", "need", "know", "think", "really",
    "what", "how", "why", "when", "who", "which", "there", "here", "out", "up",
    "about", "into", "than", "too", "very", "more", "most", "some", "any", "all",
    "one", "also", "because", "now", "still", "even", "much", "make", "made",
    "thing", "things", "way", "lot", "yeah", "ok", "okay", "well", "good",
}


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text)]


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


@dataclass
class Metrics:
    """Computed signals for one window of human messages."""

    label: str
    start: datetime | None
    end: datetime | None

    message_count: int = 0
    active_days: int = 0
    msgs_per_active_day: float = 0.0

    mean_words: float = 0.0
    median_words: float = 0.0

    late_night_ratio: float = 0.0  # share of msgs posted 00:00-05:59 local-UTC
    hour_histogram: dict[int, int] = field(default_factory=dict)

    sleep_mentions: int = 0
    sleep_mentions_per_100: float = 0.0

    self_ref_rate: float = 0.0  # self-ref tokens / total tokens
    valence: float = 0.0  # (pos - neg) / (pos + neg), in [-1, 1]
    grandiosity_per_100: float = 0.0

    vocab_diversity: float = 0.0  # type-token ratio (length-normalized)

    top_keywords: list[tuple[str, int]] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["start"] = self.start.isoformat() if self.start else None
        d["end"] = self.end.isoformat() if self.end else None
        return d


def compute(messages: Iterable[Message], label: str) -> Metrics:
    """Compute :class:`Metrics` over the *human* messages provided.

    Non-human messages are ignored; pass already-filtered windows.
    """
    msgs = [m for m in messages if m.is_human]
    stamps = [m.created_at for m in msgs if m.created_at]
    start = min(stamps) if stamps else None
    end = max(stamps) if stamps else None

    m = Metrics(label=label, start=start, end=end, message_count=len(msgs))
    if not msgs:
        return m

    # Pace / activity.
    days = {s.date() for s in stamps}
    m.active_days = len(days)
    m.msgs_per_active_day = round(_safe_div(len(msgs), max(1, len(days))), 2)

    # Length.
    word_counts = [len(_tokens(msg.text)) for msg in msgs]
    m.mean_words = round(_safe_div(sum(word_counts), len(word_counts)), 1)
    m.median_words = round(_median(word_counts), 1)

    # Posting hours.
    hist: Counter[int] = Counter(s.hour for s in stamps)
    m.hour_histogram = dict(sorted(hist.items()))
    late = sum(c for h, c in hist.items() if 0 <= h < 6)
    m.late_night_ratio = round(_safe_div(late, len(stamps)), 3) if stamps else 0.0

    # Token-level passes.
    all_tokens: list[str] = []
    self_ref = pos = neg = grand = sleep = 0
    for msg in msgs:
        toks = _tokens(msg.text)
        all_tokens.extend(toks)
        for t in toks:
            if t in SELF_REF:
                self_ref += 1
            if t in POSITIVE_WORDS:
                pos += 1
            if t in NEGATIVE_WORDS:
                neg += 1
            if t in GRANDIOSE_WORDS:
                grand += 1
        sleep += len(SLEEP_RE.findall(msg.text))

    total_tokens = len(all_tokens)
    m.self_ref_rate = round(_safe_div(self_ref, total_tokens), 4)
    m.valence = round(_safe_div(pos - neg, pos + neg), 3) if (pos + neg) else 0.0
    m.grandiosity_per_100 = round(_safe_div(grand * 100, total_tokens), 3)
    m.sleep_mentions = sleep
    m.sleep_mentions_per_100 = round(_safe_div(sleep * 100, len(msgs)), 2)

    # Vocabulary diversity, normalized for length so windows compare fairly.
    # (Raw type-token ratio shrinks as text grows; divide types by sqrt(tokens).)
    unique = len(set(all_tokens))
    m.vocab_diversity = round(_safe_div(unique, math.sqrt(total_tokens)), 3) if total_tokens else 0.0

    # Fixation / topic keywords.
    content_tokens = [t for t in all_tokens if t not in _STOPWORDS and len(t) > 2]
    m.top_keywords = Counter(content_tokens).most_common(15)

    return m


# --------------------------------------------------------------------------- #
# Deltas between two windows
# --------------------------------------------------------------------------- #

@dataclass
class Delta:
    field: str
    baseline: float
    recent: float

    @property
    def change(self) -> float:
        return round(self.recent - self.baseline, 4)

    @property
    def pct_change(self) -> float | None:
        if self.baseline == 0:
            return None
        return round((self.recent - self.baseline) / abs(self.baseline) * 100, 1)


_DELTA_FIELDS = [
    "msgs_per_active_day",
    "mean_words",
    "median_words",
    "late_night_ratio",
    "sleep_mentions_per_100",
    "self_ref_rate",
    "valence",
    "grandiosity_per_100",
    "vocab_diversity",
]


def deltas(baseline: Metrics, recent: Metrics) -> list[Delta]:
    """Field-by-field change from baseline -> recent."""
    out = []
    for f in _DELTA_FIELDS:
        out.append(Delta(f, float(getattr(baseline, f)), float(getattr(recent, f))))
    return out


def emerging_keywords(baseline: Metrics, recent: Metrics, top: int = 10) -> list[str]:
    """Keywords prominent in the recent window but not the baseline."""
    base = {k for k, _ in baseline.top_keywords}
    return [k for k, _ in recent.top_keywords if k not in base][:top]
