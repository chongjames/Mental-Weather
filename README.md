# Mental Weather Report

A small tool that reads your **Claude chat history** and gives you a periodic
*Mental Weather Report* — plain-language observations about shifts in your
energy, pace, tone, sleep signals, fixation, and self-reference over time.

**Observations, not diagnoses.** This is a personal reflection tool, in the
spirit of mood journaling with pattern recognition. It does **not** screen for
or label any condition, and it never will — that guardrail is built into the
code and the narrative prompt. It sees only a thin, self-selected slice of your
life (what you type to Claude) and cannot see your sleep, behavior, health, or
relationships. If something it surfaces resonates or worries you, talk to a
person you trust or a professional.

## Why a tool (and not just asking Claude in chat)

Inside a chat, `conversation_search` / `recent_chats` are **scoped to the
current project**, so Claude can't see across all your projects at once. A
**data export**, by contrast, contains *every* conversation regardless of
project. This tool runs over that export, giving the complete cross-project
view.

## Getting your data

1. In Claude: **Settings → Privacy → Export data** (you'll get an email with a
   zip).
2. Unzip it. The file you want is **`conversations.json`**.

Your data never leaves your machine for the metrics step. The optional
narrative step sends *computed metrics and a few short snippets* (not your full
history) to the Claude API.

## Install

```bash
pip install -e .            # metrics-only, zero dependencies
pip install -e '.[narrative]'   # adds the optional Claude-API narrative
```

Requires Python 3.10+.

## Usage

```bash
# Metrics-only report to your terminal
mental-weather conversations.json --no-narrative

# Full report (metrics + Claude narrative) written to a file
export ANTHROPIC_API_KEY=sk-ant-...
mental-weather conversations.json -o weather.md

# Preview the FULL report (with a weather section) offline — no key, no network
mental-weather conversations.json --fake-narrative
```

Useful flags:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--recent-days` | `14` | Length of the "recent" window |
| `--baseline-days` | `90` | Length of the "baseline" window before it |
| `--weeks` | `12` | Weeks shown in the trend table |
| `--tz` | `UTC` | Timezone for hour-of-day / late-night / per-day signals (e.g. `+08:00` or `Australia/Perth`) |
| `--no-narrative` | off | Skip the API call, metrics only |
| `--fake-narrative` | off | Fill the weather section with a deterministic offline stub |
| `--model` | `claude-opus-4-8` | Model for the narrative |
| `-o, --output` | stdout | Write markdown to a file |

If no API key (or the `anthropic` SDK) is present, it silently produces a
metrics-only report.

### Trying the narrative without an API key

The narrative step is the only part that calls the Claude API. To see and test
what a complete report *with* a weather section looks like — without a key, the
SDK, or any network — use the offline stub:

```bash
mental-weather tests/fixtures/sample_export.json --fake-narrative
# or, equivalently, drive it from the environment:
MENTAL_WEATHER_FAKE_NARRATIVE=1 mental-weather tests/fixtures/sample_export.json
```

The stub is **not a model** — it runs the full narrative path (payload
assembly, snippet sampling, report integration) and writes a short,
deterministic read of the largest signal moves, clearly labeled
`[stub narrative — no API call]`. It exists purely so the narrative path can be
previewed and tested. When you do have a key, drop the flag to get the real
Claude-written narrative.

## What it measures

All metrics are **deterministic and offline**, computed only over *your*
(human) messages. They are deliberately blunt — signals to look at, not
measurements of a person:

- **Pace** — messages per active day, message length (mean/median words).
- **Posting hours** — full hour histogram and a `late_night_ratio`
  (share posted 00:00–05:59). Computed in UTC by default; pass `--tz` (e.g.
  `--tz Australia/Perth` or `--tz +08:00`) to bin by your **local** time —
  otherwise "late night" means late night in UTC, not where you live.
- **Sleep signals** — mentions of sleep/tiredness/being up late.
- **Self-reference** — first-person token rate (`I`, `me`, `my`).
- **Valence** — a *crude* positive-minus-negative word balance (−1…1).
- **Grandiosity** — a *crude* count of grandiose words per 100 tokens.
- **Vocabulary diversity** — length-normalized vocabulary range.
- **Fixation / emerging topics** — top keywords, and which topics are new in
  the recent window vs the baseline.

The report compares a **recent window** against the **baseline** before it,
shows a per-week trend table, and (optionally) asks Claude to write the
short "weather" narrative on top of those signals.

The "valence" and "grandiosity" lexicons are small, embedded word lists. They
are crude by design and labeled as such — treat them as rough needles, not
gauges.

## Layout

```
mental_weather/
  parse.py       # load + normalize a Claude export (robust to format drift)
  metrics.py     # deterministic per-window signals + deltas
  windows.py     # baseline-vs-recent split and weekly trend
  narrative.py   # optional Claude-API narrative (responsible-framing prompt)
  report.py      # assemble the markdown report
  cli.py         # `mental-weather` entrypoint
tests/           # parse/metrics/report tests + a sample export fixture
```

## Development

```bash
pip install -e '.[dev]'
pytest -q
```

There's a sample export at `tests/fixtures/sample_export.json` you can run
against directly:

```bash
mental-weather tests/fixtures/sample_export.json --no-narrative
```

## License

MIT
