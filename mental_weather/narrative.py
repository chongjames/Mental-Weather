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


def is_available() -> bool:
    """True if we can plausibly call the API (key present and SDK importable)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def generate(ni: NarrativeInput, model: str = DEFAULT_MODEL, max_tokens: int = 700) -> str:
    """Call Claude to produce the narrative. Raises if unavailable."""
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
