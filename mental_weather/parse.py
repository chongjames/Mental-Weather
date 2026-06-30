"""Load and normalize a Claude / Anthropic data export.

When you request a data export from Anthropic (Settings -> Privacy ->
Export data) you receive a zip containing ``conversations.json`` (and
usually ``projects.json``, ``users.json``). Crucially, ``conversations.json``
contains *every* conversation regardless of which project it lived in -- so
analyzing it gives the cross-project view that ``conversation_search`` cannot.

This module is deliberately defensive about the export shape, which has
drifted across versions:

* The top level may be a ``list`` of conversations or a ``dict`` wrapping one
  (e.g. ``{"conversations": [...]}``).
* A message's text may live in a flat ``text`` field, or be split across a
  ``content`` array of typed blocks (``{"type": "text", "text": "..."}``).
* Sender may be keyed ``sender`` or ``role`` with values
  ``human``/``user`` and ``assistant``.
* Timestamps are ISO-8601, sometimes with a trailing ``Z``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass
class Message:
    """A single message, normalized."""

    conversation_uuid: str
    conversation_name: str
    sender: str  # "human" or "assistant"
    text: str
    created_at: datetime | None
    project: str | None = None

    @property
    def is_human(self) -> bool:
        return self.sender == "human"


@dataclass
class Export:
    """A parsed export plus a few cheap conveniences."""

    messages: list[Message] = field(default_factory=list)

    def human_messages(self) -> list[Message]:
        return [m for m in self.messages if m.is_human]

    def timespan(self) -> tuple[datetime | None, datetime | None]:
        stamps = [m.created_at for m in self.messages if m.created_at]
        if not stamps:
            return (None, None)
        return (min(stamps), max(stamps))

    def conversation_count(self) -> int:
        return len({m.conversation_uuid for m in self.messages})


# --------------------------------------------------------------------------- #
# Normalization helpers
# --------------------------------------------------------------------------- #

_HUMAN_SENDERS = {"human", "user", "you"}


def _normalize_sender(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s in _HUMAN_SENDERS:
        return "human"
    return "assistant"


def parse_timestamp(raw: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime.

    Returns ``None`` for anything unparseable rather than raising, so one
    malformed record never sinks a whole export.
    """
    if not raw:
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    # Python's fromisoformat handles "Z" only on 3.11+; normalize for safety.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Fall back to a couple of common explicit formats.
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_text(msg: dict[str, Any]) -> str:
    """Pull message text, preferring concatenated content blocks."""
    parts: list[str] = []
    content = msg.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") in (None, "text") and block.get("text"):
                    parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
    if parts:
        return "\n".join(parts).strip()
    # Fall back to the flat field.
    return str(msg.get("text") or "").strip()


def _iter_conversations(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, list):
        yield from (c for c in data if isinstance(c, dict))
    elif isinstance(data, dict):
        for key in ("conversations", "data", "items"):
            inner = data.get(key)
            if isinstance(inner, list):
                yield from (c for c in inner if isinstance(c, dict))
                return
        # A single conversation object.
        if "chat_messages" in data or "messages" in data:
            yield data


def _conversation_messages(conv: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("chat_messages", "messages"):
        msgs = conv.get(key)
        if isinstance(msgs, list):
            return [m for m in msgs if isinstance(m, dict)]
    return []


def _project_name(conv: dict[str, Any]) -> str | None:
    proj = conv.get("project") or conv.get("project_uuid") or conv.get("conversation_template")
    if isinstance(proj, dict):
        return proj.get("name") or proj.get("uuid")
    if isinstance(proj, str):
        return proj
    return None


def from_conversations(data: Any) -> Export:
    """Build an :class:`Export` from already-loaded JSON data."""
    messages: list[Message] = []
    for conv in _iter_conversations(data):
        conv_uuid = str(conv.get("uuid") or conv.get("id") or "")
        conv_name = str(conv.get("name") or conv.get("title") or "(untitled)")
        project = _project_name(conv)
        for raw in _conversation_messages(conv):
            text = _extract_text(raw)
            if not text:
                continue
            messages.append(
                Message(
                    conversation_uuid=conv_uuid,
                    conversation_name=conv_name,
                    sender=_normalize_sender(raw.get("sender") or raw.get("role")),
                    text=text,
                    created_at=parse_timestamp(
                        raw.get("created_at") or raw.get("timestamp")
                    ),
                    project=project,
                )
            )
    messages.sort(key=lambda m: (m.created_at or datetime.min.replace(tzinfo=timezone.utc)))
    return Export(messages=messages)


def load(path: str | Path) -> Export:
    """Load an export from a ``conversations.json`` file path."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return from_conversations(data)
