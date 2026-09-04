"""Dictation modes.

A mode decides what happens to raw transcript text before it is inserted.
The cheapest mode ("raw") does nothing at all; the rest optionally hand the
text to an LLM with a rewrite instruction, the way a "voice mode" would.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass
class Mode:
    """One named way of turning speech into finished text."""

    name: str
    description: str = ""
    # "none" keeps the transcript verbatim (after local cleanup).
    # "anthropic" and "ollama" send the transcript to that provider.
    llm: str = "none"
    model: str = ""
    prompt: str = ""
    temperature: float = 0.2
    # Strip "um"/"uh" style disfluencies locally, before any LLM step.
    remove_fillers: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Mode":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    @property
    def uses_llm(self) -> bool:
        return self.llm not in ("", "none")


_CLEANUP = (
    "You are a dictation post-processor. Rewrite the user's speech transcript "
    "as clean written text. Fix punctuation, capitalisation and obvious "
    "speech-recognition slips. Do not add information, do not answer questions "
    "in the text, do not add a preamble or commentary. Return only the "
    "rewritten text."
)


def builtin_modes() -> Dict[str, Mode]:
    """The modes every install starts with."""
    return {
        "raw": Mode(
            name="raw",
            description="Verbatim transcript, local cleanup only. Fastest.",
            llm="none",
            remove_fillers=False,
        ),
        "clean": Mode(
            name="clean",
            description="Verbatim transcript with fillers and stutters removed.",
            llm="none",
            remove_fillers=True,
        ),
        "polish": Mode(
            name="polish",
            description="Light LLM pass for punctuation and grammar.",
            llm="anthropic",
            prompt=_CLEANUP,
        ),
        "email": Mode(
            name="email",
            description="Turn a spoken ramble into a short, plain email body.",
            llm="anthropic",
            prompt=(
                _CLEANUP + " Format it as the body of a brief, direct email. "
                "No subject line, no greeting unless the speaker dictated one, "
                "no sign-off unless dictated."
            ),
        ),
        "message": Mode(
            name="message",
            description="Casual chat message: short, lowercase-friendly, no fluff.",
            llm="anthropic",
            prompt=(
                _CLEANUP + " Keep it casual and short, the way a chat message "
                "reads. Preserve the speaker's tone."
            ),
        ),
        "notes": Mode(
            name="notes",
            description="Reshape spoken thoughts into terse bullet points.",
            llm="anthropic",
            prompt=(
                "You are a dictation post-processor. Turn the user's speech "
                "transcript into terse markdown bullet points capturing every "
                "point made. Do not add information. Return only the bullets."
            ),
        ),
        "code": Mode(
            name="code",
            description="Spoken identifiers and symbols rendered as code-ish text.",
            llm="anthropic",
            prompt=(
                "You are a dictation post-processor for a programmer. Convert "
                "spoken symbol names into real syntax (\"open paren\" -> \"(\", "
                "\"snake case foo bar\" -> \"foo_bar\", \"dot\" -> \".\"). Keep "
                "prose as prose. Return only the converted text."
            ),
        ),
    }


def default_modes_dict() -> Dict[str, Dict[str, Any]]:
    return {name: mode.to_dict() for name, mode in builtin_modes().items()}


def load_modes(raw: Dict[str, Any] | None) -> Dict[str, Mode]:
    """Merge user-configured modes over the built-ins."""
    modes = builtin_modes()
    for name, data in (raw or {}).items():
        if not isinstance(data, dict):
            continue
        data = dict(data)
        data.setdefault("name", name)
        modes[name] = Mode.from_dict(data)
    return modes
