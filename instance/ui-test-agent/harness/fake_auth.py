"""Dummy-only credential alias boundary used by the local test harness."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable


PROFILE_FILE = Path(__file__).parent / "fake-auth" / "profiles.json"


class UnknownProfileError(ValueError):
    """Raised when the requested fixture alias is not defined."""


def profile_metadata(alias: str) -> dict:
    """Return safe display fields for an alias, never its login values."""
    profile = _profiles().get(alias)
    if profile is None:
        raise UnknownProfileError(f"Unknown local test profile: {alias}")
    return {
        "alias": alias,
        "auth_context": profile["auth_context"],
        "org_display": profile["org_display"],
    }


def login_profile(alias: str, submit: Callable[[str, str], dict]) -> dict:
    """Submit dummy credentials inside the helper and return safe metadata.

    The callback is the boundary to a local browser/form driver. Credentials are
    passed to it only; they are never returned or included in error messages.
    """
    profile = _profiles().get(alias)
    if profile is None:
        raise UnknownProfileError(f"Unknown local test profile: {alias}")
    try:
        result = submit(profile["username"], profile["password"])
    except Exception:
        raise RuntimeError("Local profile login failed") from None
    if not result.get("authenticated"):
        return {"authenticated": False, **_safe_fields(alias, profile)}
    return {"authenticated": True, **_safe_fields(alias, profile)}


def _safe_fields(alias: str, profile: dict) -> dict:
    return {
        "alias": alias,
        "auth_context": profile["auth_context"],
        "org_display": profile["org_display"],
    }


def load_profiles() -> dict:
    """Load fixture profiles, optionally overriding one with local env values."""
    profiles = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    username = os.environ.get("UI_HARNESS_USERNAME")
    password = os.environ.get("UI_HARNESS_PASSWORD")
    if bool(username) != bool(password):
        raise ValueError("Set both UI_HARNESS_USERNAME and UI_HARNESS_PASSWORD")
    if username:
        alias = os.environ.get("UI_HARNESS_PROFILE", "viewer")
        profile = profiles.get(alias)
        if profile is None:
            raise UnknownProfileError(f"Unknown local test profile: {alias}")
        profile["username"] = username
        profile["password"] = password
    return profiles


def _profiles() -> dict:
    return load_profiles()
