"""Rotation automatique des clés API avec cooldown + auto-recovery.

Supporte Gemini (héritage) et DeepSeek (principal).

Features:
  1. Rotation circulaire: key1 → key2 → key3 → key1 (jamais bloqué)
  2. Cooldown par clé: quand une clé reçoit 429, elle est marquée "épuisée" 60s
  3. Auto-recovery: les cooldowns expirent après 60s — les clés reviennent
  4. Smart retry: si toutes les clés sont en cooldown, retourne la plus proche
"""

import os
import time

COOLDOWN_SECONDS = 60

# ── Gemini (kept for vision / audio transcription fallback) ──────────────────
_gemini_index = 0
_gemini_exhausted_until: dict[int, float] = {}


def _get_gemini_keys() -> list:
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


def _gemini_in_cooldown(index: int) -> bool:
    until = _gemini_exhausted_until.get(index)
    if until is None:
        return False
    if time.time() >= until:
        _gemini_exhausted_until.pop(index, None)
        return False
    return True


def get_gemini_key() -> str:
    global _gemini_index
    keys = _get_gemini_keys()
    if not keys:
        return ""
    for i in range(len(keys)):
        idx = (_gemini_index + i) % len(keys)
        if not _gemini_in_cooldown(idx):
            _gemini_index = idx
            return keys[idx]
    soonest_idx, soonest_time = 0, float("inf")
    for i in range(len(keys)):
        until = _gemini_exhausted_until.get(i, 0)
        if until < soonest_time:
            soonest_time = until
            soonest_idx = i
    _gemini_index = soonest_idx
    return keys[soonest_idx]


def mark_key_exhausted():
    """Mark current Gemini key as exhausted (429)."""
    _gemini_exhausted_until[_gemini_index] = time.time() + COOLDOWN_SECONDS


def rotate_gemini_key() -> str:
    global _gemini_index
    keys = _get_gemini_keys()
    if not keys:
        return ""
    _gemini_index = (_gemini_index + 1) % len(keys)
    for i in range(len(keys)):
        idx = (_gemini_index + i) % len(keys)
        if not _gemini_in_cooldown(idx):
            _gemini_index = idx
            return keys[idx]
    return keys[_gemini_index]


def get_all_keys_count() -> int:
    return max(len(_get_gemini_keys()), 1)


def has_keys() -> bool:
    return len(_get_gemini_keys()) > 0


def all_keys_exhausted() -> bool:
    keys = _get_gemini_keys()
    if not keys:
        return True
    return all(_gemini_in_cooldown(i) for i in range(len(keys)))


def get_recovery_wait_seconds() -> float:
    keys = _get_gemini_keys()
    for i in range(len(keys)):
        if not _gemini_in_cooldown(i):
            return 0
    soonest = min(_gemini_exhausted_until.get(i, 0) for i in range(len(keys)))
    return max(0, soonest - time.time())


# ── DeepSeek (principal LLM for all agents) ──────────────────────────────────
_ds_index = 0
_ds_exhausted_until: dict[int, float] = {}


def _get_deepseek_keys() -> list:
    keys = []
    for i in range(1, 10):
        k = os.environ.get(f"DEEPSEEK_API_KEY_{i}", "").strip()
        if k:
            keys.append(k)
    if not keys:
        single = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if single:
            keys.append(single)
    return keys


def _ds_in_cooldown(index: int) -> bool:
    until = _ds_exhausted_until.get(index)
    if until is None:
        return False
    if time.time() >= until:
        _ds_exhausted_until.pop(index, None)
        return False
    return True


def get_deepseek_key() -> str:
    """Get the current active DeepSeek key (skipping keys in cooldown)."""
    global _ds_index
    keys = _get_deepseek_keys()
    if not keys:
        return ""
    for i in range(len(keys)):
        idx = (_ds_index + i) % len(keys)
        if not _ds_in_cooldown(idx):
            _ds_index = idx
            return keys[idx]
    soonest_idx, soonest_time = 0, float("inf")
    for i in range(len(keys)):
        until = _ds_exhausted_until.get(i, 0)
        if until < soonest_time:
            soonest_time = until
            soonest_idx = i
    _ds_index = soonest_idx
    return keys[soonest_idx]


def mark_deepseek_key_exhausted():
    """Mark current DeepSeek key as exhausted (429). Starts 60s cooldown."""
    _ds_exhausted_until[_ds_index] = time.time() + COOLDOWN_SECONDS


def rotate_deepseek_key() -> str:
    """Rotate to the next available DeepSeek key."""
    global _ds_index
    keys = _get_deepseek_keys()
    if not keys:
        return ""
    _ds_index = (_ds_index + 1) % len(keys)
    for i in range(len(keys)):
        idx = (_ds_index + i) % len(keys)
        if not _ds_in_cooldown(idx):
            _ds_index = idx
            return keys[idx]
    return keys[_ds_index]


def get_deepseek_keys_count() -> int:
    return max(len(_get_deepseek_keys()), 1)


def has_deepseek_keys() -> bool:
    return len(_get_deepseek_keys()) > 0


def all_deepseek_keys_exhausted() -> bool:
    keys = _get_deepseek_keys()
    if not keys:
        return True
    return all(_ds_in_cooldown(i) for i in range(len(keys)))


def get_deepseek_recovery_wait_seconds() -> float:
    keys = _get_deepseek_keys()
    for i in range(len(keys)):
        if not _ds_in_cooldown(i):
            return 0
    soonest = min(_ds_exhausted_until.get(i, 0) for i in range(len(keys)))
    return max(0, soonest - time.time())
