import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _parse_positive_int_env(name: str, default: int) -> int:
    """Parses a positive integer from env or returns a default."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw.strip())
    except ValueError as e:
        raise ValueError(f"{name} must be an integer. Received: {raw!r}.") from e

    if value < 1:
        raise ValueError(f"{name} must be >= 1. Received: {value}.")

    return value


def _parse_non_negative_int_env(name: str, default: int) -> int:
    """Parses a non-negative integer from env or returns a default."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    try:
        value = int(raw.strip())
    except ValueError as e:
        raise ValueError(f"{name} must be an integer. Received: {raw!r}.") from e

    if value < 0:
        raise ValueError(f"{name} must be >= 0. Received: {value}.")

    return value


def _build_char_limits() -> dict[str, dict[str, int]]:
    """Builds field character constraints from .env with sane defaults."""
    limits = {
        "work_summary": {
            "min": _parse_positive_int_env("WORK_SUMMARY_MIN_CHARS", 300),
            "max": _parse_positive_int_env("WORK_SUMMARY_MAX_CHARS", 500),
        },
        "learnings": {
            "min": _parse_positive_int_env("LEARNINGS_MIN_CHARS", 250),
            "max": _parse_positive_int_env("LEARNINGS_MAX_CHARS", 500),
        },
        "blockers": {
            "min": _parse_positive_int_env("BLOCKERS_MIN_CHARS", 100),
            "max": _parse_positive_int_env("BLOCKERS_MAX_CHARS", 200),
        },
    }

    for field, bounds in limits.items():
        if bounds["min"] > bounds["max"]:
            field_upper = field.upper()
            raise ValueError(
                f"{field_upper}_MIN_CHARS cannot be greater than {field_upper}_MAX_CHARS. "
                f"Received min={bounds['min']}, max={bounds['max']}."
            )

    return limits


def load_config() -> dict[str, Any]:
    """Loads and validates the environment values required for the bot."""
    load_dotenv()
    
    email = os.getenv("CLG_EMAIL")
    password = os.getenv("CLG_PASS")
    gemini_key = os.getenv("GEMINI_API_KEY")
    compulsory_string = os.getenv("COMPULSORY_SKILLS", "Git, Docker")
    
    missing = []
    if not email: missing.append("CLG_EMAIL")
    if not password: missing.append("CLG_PASS")
    if not gemini_key: missing.append("GEMINI_API_KEY")
    
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}\nPlease update your .env file.")

    char_limits = _build_char_limits()

    return {
        "EMAIL": email,
        "PASSWORD": password,
        "GEMINI_KEY": gemini_key,
        "COMPULSORY_SKILLS": [s.strip() for s in compulsory_string.split(",") if s.strip()],
        "FIELD_CHAR_LIMITS": char_limits,
        "FIELD_CHAR_TOLERANCE": _parse_non_negative_int_env("FIELD_CHAR_TOLERANCE", 40),
        "LOGIN_URL": "https://vtu.internyet.in/sign-in",
        "DIARY_URL": "https://vtu.internyet.in/dashboard/student/student-diary",
        "STATE_FILE": Path("browser_state.json")
    }
