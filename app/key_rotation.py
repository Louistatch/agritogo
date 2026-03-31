"""Rotation automatique des clés API Gemini."""

import os

_gemini_keys = []
_current_index = 0


def _load_keys():
    global _gemini_keys
    if not _gemini_keys:
        keys = []
        for i in range(1, 10):
            k = os.environ.get(f"GEMINI_API_KEY_{i}")
            if k:
                keys.append(k)
        # Fallback to single key
        if not keys:
            single = os.environ.get("GEMINI_API_KEY", "")
            if single:
                keys.append(single)
        _gemini_keys = keys


def get_gemini_key() -> str:
    """Get the current Gemini API key."""
    _load_keys()
    if not _gemini_keys:
        return ""
    return _gemini_keys[_current_index % len(_gemini_keys)]


def rotate_gemini_key() -> str:
    """Rotate to the next Gemini API key. Returns the new key."""
    global _current_index
    _load_keys()
    if not _gemini_keys:
        return ""
    _current_index = (_current_index + 1) % len(_gemini_keys)
    new_key = _gemini_keys[_current_index]
    return new_key


def get_all_keys_count() -> int:
    _load_keys()
    return len(_gemini_keys)
