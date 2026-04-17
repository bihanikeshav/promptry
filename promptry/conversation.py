"""Multi-turn conversation data model.

Use ``Conversation`` to represent a chat/agent/copilot session as an
ordered list of ``Turn`` objects. Combine with the conversation-level
assertions in :mod:`promptry.assertions` to evaluate chatbot flows.

Example::

    from promptry import Conversation

    conv = Conversation()
    conv.add("user", "Hi, what's the weather?")
    conv.add("assistant", my_bot(conv))
    conv.add("user", "And tomorrow?")
    conv.add("assistant", my_bot(conv))

The class also offers ``from_openai`` / ``from_anthropic`` so you can drop
in an existing messages list from either SDK.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Turn:
    """A single turn in a conversation.

    Attributes:
        role: "user", "assistant", or "system".
        content: The textual content of the turn.
        tools: Optional list of tool call dicts (for assistant turns that
               invoke tools).
        metadata: Free-form metadata, e.g. latency, cost, token counts.
    """
    role: str
    content: str
    tools: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class Conversation:
    """An ordered list of turns representing a multi-turn exchange."""
    turns: list[Turn] = field(default_factory=list)

    def add(self, role: str, content: str, **kwargs: Any) -> "Conversation":
        """Append a turn. Returns self so calls chain fluently.

        Example::

            conv = Conversation().add("user", "hi").add("assistant", "hello")
        """
        self.turns.append(Turn(role=role, content=content, **kwargs))
        return self

    def last(self, role: str | None = None) -> Turn | None:
        """Return the last turn, optionally filtered by role.

        Returns None if no turn matches.
        """
        if role is None:
            return self.turns[-1] if self.turns else None
        for turn in reversed(self.turns):
            if turn.role == role:
                return turn
        return None

    def assistant_turns(self) -> list[Turn]:
        """All turns with role == 'assistant', in order."""
        return [t for t in self.turns if t.role == "assistant"]

    def user_turns(self) -> list[Turn]:
        """All turns with role == 'user', in order."""
        return [t for t in self.turns if t.role == "user"]

    def __len__(self) -> int:
        return len(self.turns)

    def __iter__(self):
        return iter(self.turns)

    # -- converters ---------------------------------------------------------

    @classmethod
    def from_openai(cls, messages: list[dict]) -> "Conversation":
        """Convert an OpenAI chat-completions messages list.

        OpenAI messages look like::

            [
                {"role": "system", "content": "..."},
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "...",
                 "tool_calls": [{...}]},
                {"role": "tool", "content": "...", "tool_call_id": "..."},
            ]

        ``tool_calls`` on an assistant turn are captured in ``Turn.tools``.
        ``tool`` role messages are preserved with their content and the
        ``tool_call_id`` stored in metadata.
        """
        conv = cls()
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content") or ""
            # content can be a list of parts for multimodal -- flatten text
            if isinstance(content, list):
                parts = []
                for p in content:
                    if isinstance(p, dict) and "text" in p:
                        parts.append(p["text"])
                    elif isinstance(p, str):
                        parts.append(p)
                content = "\n".join(parts)

            tools: list[dict] = []
            metadata: dict = {}
            if role == "assistant" and msg.get("tool_calls"):
                tools = list(msg["tool_calls"])
            if "tool_call_id" in msg:
                metadata["tool_call_id"] = msg["tool_call_id"]
            if "name" in msg:
                metadata["name"] = msg["name"]

            conv.turns.append(Turn(
                role=role,
                content=str(content),
                tools=tools,
                metadata=metadata,
            ))
        return conv

    @classmethod
    def from_anthropic(cls, messages: list[dict]) -> "Conversation":
        """Convert an Anthropic messages list.

        Anthropic messages look like::

            [
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": [
                    {"type": "text", "text": "..."},
                    {"type": "tool_use", "id": "...", "name": "...",
                     "input": {...}},
                ]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "...",
                     "content": "..."},
                ]},
            ]

        Text parts are concatenated into ``Turn.content``; ``tool_use``
        blocks are captured in ``Turn.tools``.
        """
        conv = cls()
        for msg in messages:
            role = msg.get("role", "")
            raw = msg.get("content", "")

            text_parts: list[str] = []
            tools: list[dict] = []

            if isinstance(raw, str):
                text_parts.append(raw)
            elif isinstance(raw, list):
                for block in raw:
                    if not isinstance(block, dict):
                        text_parts.append(str(block))
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        text_parts.append(block.get("text", ""))
                    elif btype == "tool_use":
                        tools.append({
                            "id": block.get("id"),
                            "name": block.get("name"),
                            "input": block.get("input", {}),
                        })
                    elif btype == "tool_result":
                        # tool results come back on user turns
                        content = block.get("content", "")
                        if isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "text":
                                    text_parts.append(c.get("text", ""))
                                else:
                                    text_parts.append(str(c))
                        else:
                            text_parts.append(str(content))
            else:
                text_parts.append(str(raw))

            conv.turns.append(Turn(
                role=role,
                content="\n".join(p for p in text_parts if p),
                tools=tools,
            ))
        return conv
