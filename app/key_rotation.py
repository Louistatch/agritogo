"""Rotation automatique des clés API Gemini."""

import os

_current_index = 0


def _get_keys() -> list:
    """Always read fresh from os.environ — no caching."""
    keys = []
    for i in range(1, 10):
        k = os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
        if k:
            keys.append(k)
    if not keys:
        single = os.environ.get("GEMINI_API_KEY", "").strip()
        if single:
            keys.append(single)
    return keys


def get_gemini_key() -> str:
    """Get the current Gemini API key — always fresh from env."""
    global _current_index
    keys = _get_keys()
    if not keys:
        return ""
    return keys[_current_index % len(keys)]


def rotate_gemini_key() -> str:
    """Rotate to the next key."""
    global _current_index
    keys = _get_keys()
    if not keys:
        return ""
    _current_index = (_current_index + 1) % len(keys)
    return keys[_current_index]


def get_all_keys_count() -> int:
    return max(len(_get_keys()), 1)


def has_keys() -> bool:
    return len(_get_keys()) > 0
