"""The EventProvider seam (contracts/engine-interface.md, research R6).

The engine depends only on `EventProvider`; it never imports the anthropic client
directly. `ClaudeProvider` (production) wraps the real client and is constructed only in
cli.py; `FakeProvider` (tests) returns scripted events with no network.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from ..models import EventType, MatchState, Side
from . import prompt


@dataclass
class ProposedEvent:
    """The model's proposal for one moment — only the fields the model MAY set."""
    type: EventType
    team_side: Optional[Side] = None
    actor_id: Optional[str] = None
    secondary_id: Optional[str] = None
    commentary: str = ""


@dataclass
class ProviderError:
    """A recoverable provider failure (API error/timeout). A value, not an exception."""
    message: str


@runtime_checkable
class EventProvider(Protocol):
    def propose(self, state: MatchState, prompt_version: str) -> ProposedEvent | ProviderError:
        ...


class FakeProvider:
    """Returns scripted proposals/errors for tests. No network.

    `script` items may be: a ProposedEvent, a ProviderError, or a callable
    ``fn(state) -> ProposedEvent | ProviderError``. Cycles/keeps returning the last item
    (a NOTHING by default) once exhausted so a match always runs to completion.
    """

    def __init__(self, script: Optional[list] = None):
        self._script = list(script or [])
        self._i = 0

    def propose(self, state: MatchState, prompt_version: str) -> ProposedEvent | ProviderError:
        if self._i < len(self._script):
            item = self._script[self._i]
            self._i += 1
        else:
            item = ProposedEvent(EventType.NOTHING, None, None, None, "Quiet spell.")
        return item(state) if callable(item) else item


class ClaudeProvider:
    """Production provider: one Claude Haiku round-trip per moment (T016).

    Uses structured output via ``output_config.format`` so the response is a well-formed
    proposed-event object; code re-validates it (validate.py) before it becomes state.
    The `anthropic` import is lazy so importing this module never requires the SDK.
    """

    def __init__(self, client=None, model: str = "claude-haiku-4-5"):
        if client is None:
            import anthropic  # lazy: tests never import the SDK
            client = anthropic.Anthropic()
        self._client = client
        self._model = model

    def propose(self, state: MatchState, prompt_version: str) -> ProposedEvent | ProviderError:
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=512,
                temperature=prompt.MATCH_TEMPERATURE,
                system=prompt.build_system(),
                messages=prompt.build_messages(state),
                output_config={"format": {"type": "json_schema",
                                          "schema": prompt.PROPOSED_EVENT_SCHEMA}},
            )
            text = next(b.text for b in response.content if b.type == "text")
            data = json.loads(text)
            return ProposedEvent(
                type=EventType(data["type"]),
                team_side=data.get("team_side"),
                actor_id=data.get("actor_id"),
                secondary_id=data.get("secondary_id"),
                commentary=data.get("commentary", ""),
            )
        except Exception as exc:  # noqa: BLE001 — any failure degrades to the fallback
            return ProviderError(f"{type(exc).__name__}: {exc}")
