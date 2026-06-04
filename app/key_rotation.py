"""Rotation automatique des clés API Gemini avec cooldown + auto-recovery.

Features:
  1. Rotation circulaire: key1 → key2 → key3 → key1 (jamais bloqué)
  2. Cooldown par clé: quand une clé reçoit 429, elle est marquée "épuisée" 60s
  3. Auto-recovery: les cooldowns expirent après 60s — les clés reviennent
  4. Smart retry: si toutes les clés sont en cooldown, retourne la plus proche
"""

import os
import time

COOLDOWN_SECONDS = 60

_current_index = 0
_exhausted_until: dict[int, float] = {}  # key_index → timestamp when cooldown expires


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


def _is_in_cooldown(index: int) -> bool:
    """Check if a key index is currently in cooldown."""
    until = _exhausted_until.get(index)
    if until is None:
        return False
    if time.time() >= until:
        _exhausted_until.pop(index, None)  # Cooldown expired
        return False
    return True


def get_gemini_key() -> str:
    """Get the current active Gemini key (skipping keys in cooldown)."""
    global _current_index
    keys = _get_keys()
    if not keys:
        return ""

    # Try to find a key not in cooldown
    for i in range(len(keys)):
        idx = (_current_index + i) % len(keys)
        if not _is_in_cooldown(idx):
            _current_index = idx
            return keys[idx]

    # All in cooldown — return the one recovering soonest
    soonest_idx = 0
    soonest_time = float("inf")
    for i in range(len(keys)):
        until = _exhausted_until.get(i, 0)
        if until < soonest_time:
            soonest_time = until
            soonest_idx = i
    _current_index = soonest_idx
    return keys[soonest_idx]


def mark_key_exhausted():
    """Mark current key as exhausted (429). Starts 60s cooldown."""
    _exhausted_until[_current_index] = time.time() + COOLDOWN_SECONDS


def rotate_gemini_key() -> str:
    """Rotate to the next available key. Skips keys in cooldown."""
    global _current_index
    keys = _get_keys()
    if not keys:
        return ""

    _current_index = (_current_index + 1) % len(keys)

    # Skip keys in cooldown
    for i in range(len(keys)):
        idx = (_current_index + i) % len(keys)
        if not _is_in_cooldown(idx):
            _current_index = idx
            return keys[idx]

    return keys[_current_index]


def get_all_keys_count() -> int:
    return max(len(_get_keys()), 1)


def has_keys() -> bool:
    return len(_get_keys()) > 0


def all_keys_exhausted() -> bool:
    """Are ALL keys currently in cooldown?"""
    keys = _get_keys()
    if not keys:
        return True
    return all(_is_in_cooldown(i) for i in range(len(keys)))


def get_recovery_wait_seconds() -> float:
    """Seconds until the next key recovers. 0 if one is ready."""
    keys = _get_keys()
    for i in range(len(keys)):
        if not _is_in_cooldown(i):
            return 0
    soonest = min(_exhausted_until.get(i, 0) for i in range(len(keys)))
    return max(0, soonest - time.time())
