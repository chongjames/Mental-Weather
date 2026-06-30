"""Command-line entrypoint: ``mental-weather path/to/conversations.json``."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import __version__, metrics, narrative, parse, report, windows


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mental-weather",
        description=(
            "Generate a Mental Weather Report from a Claude data export. "
            "Reads patterns across ALL your conversations and projects. "
            "Observations, not diagnoses."
        ),
    )
    p.add_argument(
        "export",
        help="Path to conversations.json from your Anthropic data export.",
    )
    p.add_argument(
        "-o", "--output",
        help="Write the markdown report to this file (default: stdout).",
    )
    p.add_argument(
        "--recent-days", type=int, default=14,
        help="Length of the recent window in days (default: 14).",
    )
    p.add_argument(
        "--baseline-days", type=int, default=90,
        help="Length of the baseline window preceding it (default: 90).",
    )
    p.add_argument(
        "--weeks", type=int, default=12,
        help="How many weeks to show in the trend table (default: 12).",
    )
    p.add_argument(
        "--tz", default=None,
        help="Timezone for hour-of-day, late-night, and per-day/week signals. "
             "Accepts a fixed offset ('+08:00', 'UTC+8') or an IANA name "
             "('Australia/Perth'). Defaults to UTC.",
    )
    p.add_argument(
        "--no-narrative", action="store_true",
        help="Skip the Claude API narrative even if a key is available.",
    )
    p.add_argument(
        "--fake-narrative", action="store_true",
        help="Use a deterministic offline stub for the narrative instead of "
             "calling the API (preview/test the full report with no key).",
    )
    p.add_argument(
        "--model", default=narrative.DEFAULT_MODEL,
        help=f"Model for the narrative (default: {narrative.DEFAULT_MODEL}).",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        export = parse.load(args.export)
    except FileNotFoundError:
        print(f"error: file not found: {args.export}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: could not parse export as JSON: {exc}", file=sys.stderr)
        return 2

    if not export.human_messages():
        print(
            "error: no human messages found in export. Is this a "
            "conversations.json from an Anthropic data export?",
            file=sys.stderr,
        )
        return 1

    if args.tz:
        try:
            export = parse.with_timezone(export, parse.resolve_tz(args.tz))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    split = windows.split(
        export, recent_days=args.recent_days, baseline_days=args.baseline_days
    )

    narr: str | None = None
    if not args.no_narrative:
        if narrative.is_available(fake=args.fake_narrative):
            ni = narrative.NarrativeInput(
                baseline=split.baseline,
                recent=split.recent,
                deltas=metrics.deltas(split.baseline, split.recent),
                emerging_keywords=metrics.emerging_keywords(
                    split.baseline, split.recent
                ),
                samples=narrative.sample_snippets(split.recent_msgs),
            )
            try:
                narr = narrative.generate(
                    ni, model=args.model, fake=args.fake_narrative
                )
            except Exception as exc:  # noqa: BLE001 - never let the narrative sink the report
                print(f"warning: narrative step failed ({exc}); "
                      "continuing with metrics only.", file=sys.stderr)
        else:
            print(
                "note: no ANTHROPIC_API_KEY / anthropic SDK found — "
                "generating metrics-only report. Install with "
                "`pip install 'mental-weather[narrative]'` and set the key, "
                "or pass --fake-narrative to preview the full report offline.",
                file=sys.stderr,
            )

    md = report.build(
        export, split, narrative=narr, weeks=args.weeks,
        generated_at=datetime.now(timezone.utc),
        tz_label=args.tz or "UTC",
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"wrote report to {args.output}", file=sys.stderr)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
