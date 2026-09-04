"""Local text cleanup applied to every transcript, before any LLM step.

All of it is pure string work: no network, no model, microseconds. This is
what makes "raw" and "clean" modes feel instant.
"""

from __future__ import annotations

import re
from typing import Dict

# Whisper emits these bracketed event tags when it hears non-speech.
_ARTIFACT_RE = re.compile(r"[\[\(](?:BLANK_AUDIO|INAUDIBLE|MUSIC|SILENCE|NOISE|"
                          r"(?:[a-z ]{1,30}(?:ing|noise|music|sound)))[\]\)]",
                          re.IGNORECASE)

# Standalone disfluencies. Kept deliberately short: over-eager filler removal
# eats real words ("I like it" must survive).
_FILLERS = ("um", "umm", "uh", "uhh", "erm", "ahh", "mmm", "hmm")
# A filler usually arrives wrapped in commas ("so, um, then"). Eat those too,
# or removal leaves a dangling comma where no pause belongs.
_FILLER_RE = re.compile(r",?\s*(?<!\w)(?:%s)(?!\w)\s*,?" % "|".join(_FILLERS),
                        re.IGNORECASE)

# "the the cat" -> "the cat". Only for short function words, so "had had"
# and deliberate repetition of content words survive.
_STUTTER_WORDS = ("the", "a", "i", "to", "and", "of", "that", "it", "is", "so", "but")
_STUTTER_RE = re.compile(r"(?<!\w)(%s)(\s+\1)+(?!\w)" % "|".join(_STUTTER_WORDS),
                         re.IGNORECASE)

_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?%)\]}])")
_SPACE_AFTER_OPEN_RE = re.compile(r"([(\[{])\s+")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_SENTENCE_START_RE = re.compile(r"(^|[.!?]\s+|\n\s*)([a-z])")
# Dictated "i" is almost always the pronoun.
_LONE_I_RE = re.compile(r"(?<![\w'])i(?![\w'])")


def strip_artifacts(text: str) -> str:
    return _ARTIFACT_RE.sub(" ", text)


def remove_fillers(text: str) -> str:
    return _FILLER_RE.sub(" ", text)


def collapse_stutters(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _STUTTER_RE.sub(r"\1", text)
    return text


def tidy_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = _MULTISPACE_RE.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN_RE.sub(r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return text.strip()


def capitalize_sentences(text: str) -> str:
    return _SENTENCE_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def capitalize_pronoun_i(text: str) -> str:
    return _LONE_I_RE.sub("I", text)


def _case_matched(replacement: str, matched: str) -> str:
    """Keep the speaker's casing intent when it is unambiguous."""
    if matched.isupper() and len(matched) > 1:
        return replacement.upper()
    if matched[:1].isupper() and replacement[:1].islower():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def apply_replacements(text: str, replacements: Dict[str, str]) -> str:
    """Custom vocabulary: whole-phrase, case-insensitive, longest match first."""
    if not replacements:
        return text
    for source in sorted(replacements, key=len, reverse=True):
        target = replacements[source]
        if not source.strip():
            continue
        pattern = re.compile(r"(?<!\w)" + re.escape(source.strip()) + r"(?!\w)",
                             re.IGNORECASE)
        text = pattern.sub(lambda m: _case_matched(target, m.group(0)), text)
    return text


def clean(
    text: str,
    replacements: Dict[str, str] | None = None,
    drop_fillers: bool = True,
    capitalize: bool = True,
) -> str:
    """The full local pipeline. Safe on empty or noise-only input."""
    if not text:
        return ""
    text = strip_artifacts(text)
    if drop_fillers:
        text = remove_fillers(text)
        text = collapse_stutters(text)
    text = apply_replacements(text, replacements or {})
    text = tidy_whitespace(text)
    if capitalize:
        text = capitalize_pronoun_i(text)
        text = capitalize_sentences(text)
    return text


def is_meaningful(text: str, min_chars: int = 1) -> bool:
    """False for transcripts that are only punctuation or noise tags.

    Artifacts are stripped first, so a raw "[BLANK_AUDIO]" counts as empty
    even when this is called before `clean`.
    """
    return len(re.sub(r"[^\w]", "", strip_artifacts(text))) >= min_chars
