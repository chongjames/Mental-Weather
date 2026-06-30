"""Optional Claude-API narrative layer.

The deterministic metrics are blunt numbers. This module hands those numbers
(plus a small, recent sample of message snippets) to Claude and asks for the
"weather report" -- the concise, plain-language read that the numbers alone
can't give.

The system prompt enforces the framing the user and Claude agreed on in the
original design conversation:

* Observations, not diagnoses. No clinical labels presented as conclusions.
* Plain, familiar language is fine ("feels hypomania-adjacent") *as a weather
  metaphor*, never as a verdict.
* It is allowed -- encouraged -- to say "nothing notable" when nothing shifted.

This step is entirely optional. With no API key, the report ships with metrics
and a deltas table only.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .metrics import Delta, Metrics
from .parse import Message

DEFAULT_MODEL = "claude-opus-4-8"

# Setting this env var (or passing ``fake=True`` / the ``--fake-narrative`` CLI
# flag) swaps the live API call for a deterministic, offline stub. It exists so
# the *entire* narrative path -- payload assembly, snippet sampling, report
# integration -- can be previewed and tested without a key or network.
FAKE_ENV = "MENTAL_WEATHER_FAKE_NARRATIVE"

SYSTEM_PROMPT = """\
You are writing a "Mental Weather Report": a brief, plain-language read on
shifts in how one person (the user) has been writing to Claude over time. You
are given computed metrics comparing a recent window to a baseline window, plus
a small sample of recent message snippets.

Hard rules:
- This is NOT a clinical assessment, screening, or diagnosis. Never state or
  imply that the user has, or might have, any disorder. Do not output diagnostic
  labels (e.g. "bipolar", "psychotic", "depressive episode") as conclusions.
- You MAY use familiar, vivid language as weather metaphor -- "energy is up and
  a little pressured", "tone has cooled", "skies are clear" -- because the user
  asked for concise, familiar framing. Keep it descriptive, not diagnostic.
- Anchor every observation to a concrete signal in the data. No free-floating
  claims. If a metric barely moved, say it's steady.
- It is a good and valid report to say "nothing much changed this period."
  Do not manufacture drama.
- Be direct and kind. The user explicitly asked you not to soften with endless
  caveats; the framing rules above are the only guardrails you restate.

Output format (markdown):
1. One-line headline (the "weather", e.g. "Mostly clear, energy rising").
2. 3-6 short bullet observations, each tied to a signal.
3. One closing line: an optional, low-key gut-check suggestion IF and only if
   signals genuinely shifted; otherwise a plain "steady" note.
Keep the whole thing under ~200 words.
"""


@dataclass
class NarrativeInput:
    baseline: Metrics
    recent: Metrics
    deltas: list[Delta]
    emerging_keywords: list[str]
    samples: list[str]


def _build_user_payload(ni: NarrativeInput) -> str:
    deltas_view = [
        {
            "signal": d.field,
            "baseline": d.baseline,
            "recent": d.recent,
            "change": d.change,
            "pct_change": d.pct_change,
        }
        for d in ni.deltas
    ]
    payload = {
        "metrics_legend": {
            "msgs_per_active_day": "message pace on days you were active",
            "mean_words / median_words": "message length",
            "late_night_ratio": "share of messages posted 00:00-05:59 UTC",
            "sleep_mentions_per_100": "sleep/tiredness mentions per 100 messages",
            "self_ref_rate": "first-person tokens (I, me, my) / all tokens",
            "valence": "(crude) positive-minus-negative word balance, -1..1",
            "grandiosity_per_100": "(crude) grandiose words per 100 tokens",
            "vocab_diversity": "length-normalized vocabulary range",
        },
        "deltas": deltas_view,
        "emerging_topics_recent_only": ni.emerging_keywords,
        "recent_top_keywords": ni.recent.top_keywords,
        "recent_sample_snippets": ni.samples,
    }
    return (
        "Here are the computed signals (recent window vs baseline) and a few "
        "recent snippets. Write the Mental Weather Report.\n\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )


def sample_snippets(messages: list[Message], limit: int = 12, max_chars: int = 240) -> list[str]:
    """Take a spread of recent human snippets (most recent last)."""
    msgs = [m for m in messages if m.is_human and m.text]
    msgs = sorted(msgs, key=lambda m: m.created_at or 0) if all(m.created_at for m in msgs) else msgs
    if len(msgs) <= limit:
        chosen = msgs
    else:
        step = len(msgs) / limit
        chosen = [msgs[int(i * step)] for i in range(limit)]
    out = []
    for m in chosen:
        text = " ".join(m.text.split())
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "..."
        out.append(text)
    return out


def _fake_enabled(fake: bool = False) -> bool:
    return fake or bool(os.environ.get(FAKE_ENV))


def is_available(fake: bool = False) -> bool:
    """True if we can produce a narrative.

    The fake/offline stub is always "available". Otherwise we need both an API
    key and an importable ``anthropic`` SDK.
    """
    if _fake_enabled(fake):
        return True
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


# Friendly names for signals, used by the offline stub.
_FRIENDLY = {
    "msgs_per_active_day": "message pace",
    "mean_words": "message length",
    "median_words": "message length",
    "late_night_ratio": "late-night posting",
    "sleep_mentions_per_100": "sleep/tiredness mentions",
    "self_ref_rate": "self-reference",
    "valence": "tone",
    "grandiosity_per_100": "grandiose phrasing",
    "vocab_diversity": "vocabulary range",
}


def _fake_narrative(ni: NarrativeInput) -> str:
    """Deterministic, offline stand-in for the API narrative.

    This is NOT a model. It restates the largest signal moves in plain words so
    a report *with* a weather section can be previewed and tested with no key
    and no network. It is clearly labeled as a stub so it is never mistaken for
    a real read.
    """
    def _mag(d: Delta) -> float:
        return abs(d.pct_change) if d.pct_change is not None else abs(d.change) * 100

    moved = sorted(
        (d for d in ni.deltas if _mag(d) > 1e-9), key=_mag, reverse=True
    )
    notable = moved[:4]

    if notable:
        top = notable[0]
        label = _FRIENDLY.get(top.field, top.field)
        arrow = "rising" if top.change > 0 else "easing" if top.change < 0 else "steady"
        headline = f"**[stub narrative — no API call]** {label.capitalize()} {arrow}; a few signals shifted."
    else:
        headline = "**[stub narrative — no API call]** Steady skies — nothing much moved this period."

    bullets = []
    for d in notable:
        lbl = _FRIENDLY.get(d.field, d.field)
        direction = "up" if d.change > 0 else "down"
        if d.pct_change is not None:
            bullets.append(f"- {lbl.capitalize()} {direction} ({d.baseline:g} → {d.recent:g}, {d.pct_change:+g}%).")
        else:
            bullets.append(f"- {lbl.capitalize()} {direction} ({d.baseline:g} → {d.recent:g}).")
    if not bullets:
        bullets.append("- All tracked signals held close to baseline.")
    if ni.emerging_keywords:
        kws = ", ".join(f"`{k}`" for k in ni.emerging_keywords[:5])
        bullets.append(f"- New topics surfaced: {kws}.")

    closing = (
        "_Stub preview — deterministic, not a model read. Set "
        "`ANTHROPIC_API_KEY` and install the `narrative` extra for the real one._"
    )
    return "\n".join([headline, "", *bullets, "", closing])


def generate(
    ni: NarrativeInput,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 700,
    fake: bool = False,
) -> str:
    """Produce the narrative. Returns the offline stub when fake mode is on,
    otherwise calls Claude. Raises if a live call is needed but unavailable."""
    if _fake_enabled(fake):
        return _fake_narrative(ni)

    import anthropic  # imported lazily so the metrics path needs no dependency

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_payload(ni)}],
    )
    parts = [block.text for block in resp.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts).strip()
