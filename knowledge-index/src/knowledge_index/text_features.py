from __future__ import annotations

import re
from functools import lru_cache

import jieba
from pypinyin import Style, lazy_pinyin
from pypinyin.constants import PINYIN_DICT
from pypinyin.contrib.tone_convert import to_normal

_CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)


@lru_cache(maxsize=4096)
def word_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in jieba.cut(text, cut_all=False):
        token = token.strip().lower()
        if token and any(character.isalnum() for character in token):
            tokens.append(token)
    return tuple(tokens)


@lru_cache(maxsize=4096)
def char_bigram_tokens(text: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for match in _CJK_RUN_RE.finditer(text):
        run = match.group(0)
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tuple(tokens)


@lru_cache(maxsize=4096)
def full_pinyin_tokens(text: str) -> tuple[str, ...]:
    converted = " ".join(
        lazy_pinyin(text, style=Style.NORMAL, errors=lambda value: [value])
    ).lower()
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(converted):
        tokens.extend(split_compact_pinyin(token))
    return tuple(tokens)


@lru_cache(maxsize=1)
def _pinyin_syllables() -> frozenset[str]:
    syllables: set[str] = set()
    for pronunciations in PINYIN_DICT.values():
        for pronunciation in pronunciations.split(","):
            normalized = to_normal(pronunciation).lower()
            if normalized.isascii() and normalized.isalpha():
                syllables.add(normalized)
    return frozenset(syllables)


@lru_cache(maxsize=4096)
def split_compact_pinyin(token: str) -> tuple[str, ...]:
    normalized = token.lower()
    if not normalized.isascii() or not normalized.isalpha() or len(normalized) < 2:
        return (normalized,)

    best: list[tuple[str, ...] | None] = [None] * (len(normalized) + 1)
    best[-1] = ()
    syllables = _pinyin_syllables()
    for start in range(len(normalized) - 1, -1, -1):
        candidates: list[tuple[str, ...]] = []
        for end in range(start + 1, min(start + 6, len(normalized)) + 1):
            syllable = normalized[start:end]
            remainder = best[end]
            if syllable in syllables and remainder is not None:
                candidates.append((syllable, *remainder))
        if candidates:
            best[start] = min(
                candidates,
                key=lambda value: (len(value), tuple(-len(part) for part in value)),
            )

    result = best[0]
    return result if result is not None and len(result) > 1 else (normalized,)


@lru_cache(maxsize=4096)
def pinyin_initial_tokens(text: str) -> tuple[str, ...]:
    word_initials: list[str] = []
    literal_tokens: list[str] = []
    for word in word_tokens(text):
        if not _CJK_RUN_RE.search(word):
            if word.isascii() and word.isalnum():
                literal_tokens.append(word)
            continue
        parts = lazy_pinyin(word, style=Style.FIRST_LETTER, errors="ignore")
        initial = "".join(parts).lower()
        if initial:
            word_initials.append(initial)

    # Besides individual word initials (dk, sp), index short adjacent phrases
    # (dksp). This keeps abbreviated searches useful without generating every
    # possible character n-gram for long messages.
    phrase_initials: list[str] = []
    for start in range(len(word_initials)):
        combined = ""
        for end in range(start, min(start + 4, len(word_initials))):
            combined += word_initials[end]
            if end > start:
                phrase_initials.append(combined)
    return tuple(dict.fromkeys((*word_initials, *phrase_initials, *literal_tokens)))


def index_fields(text: str) -> tuple[str, str, str, str]:
    return (
        " ".join(word_tokens(text)),
        " ".join(char_bigram_tokens(text)),
        " ".join(full_pinyin_tokens(text)),
        " ".join(pinyin_initial_tokens(text)),
    )
