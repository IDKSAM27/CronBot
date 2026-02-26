from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CliError(Exception):
    """Normalized, user-facing CLI error with clear intent and action."""

    code: str
    title: str
    intent: str
    resolution: str
    technical: str = ""
    exit_code: int = 1

    def __str__(self) -> str:
        return self.intent


def _text(exc: Exception) -> str:
    raw = str(exc).strip()
    return raw if raw else exc.__class__.__name__


def to_cli_error(exc: Exception, stage: str) -> CliError:
    """Maps any internal exception to a user-intent-focused CLI error."""
    if isinstance(exc, CliError):
        return exc

    msg = _text(exc)
    lower = msg.lower()
    stage_name = stage.strip().lower()

    if stage_name == "theme":
        return CliError(
            code="CLI_THEME_INVALID",
            title="Invalid CLI Theme",
            intent="Requested CLI theme is not supported.",
            resolution="Run with `--theme claude` or `--theme clean`.",
            technical=msg,
            exit_code=2,
        )

    if stage_name == "config":
        if any(token in lower for token in [
            "_min_chars",
            "_max_chars",
            "field_char_tolerance",
            "llm_rate_limit_retry_base_seconds",
            "llm_rate_limit_retry_max_wait_seconds",
            "llm_rate_limit_max_retries",
            "browser_default_timeout_ms",
            "browser_nav_timeout_ms",
            "must be an integer",
            "must be >= 1",
            "must be >= 0",
        ]):
            return CliError(
                code="CONFIG_INVALID_CHAR_LIMITS",
                title="Invalid Character Limit Config",
                intent="One or more numeric validation/retry values in `.env` are invalid.",
                resolution=(
                    "Set numeric values for *_MIN_CHARS, *_MAX_CHARS, FIELD_CHAR_TOLERANCE, "
                    "LLM_RATE_LIMIT_* retry values, "
                    "and ensure min is not greater than max."
                ),
                technical=msg,
            )
        if "missing required environment variables" in lower:
            return CliError(
                code="CONFIG_MISSING_ENV",
                title="Configuration Incomplete",
                intent="Required credentials are missing in `.env`.",
                resolution="Set `CLG_EMAIL`, `CLG_PASS`, and `GEMINI_API_KEY` in `.env` and rerun.",
                technical=msg,
            )
        return CliError(
            code="CONFIG_LOAD_FAILED",
            title="Configuration Load Failed",
            intent="Application could not read startup configuration.",
            resolution="Verify `.env` values and file permissions, then rerun.",
            technical=msg,
        )

    if stage_name == "llm":
        if "rate limit retries exhausted" in lower:
            return CliError(
                code="LLM_RATE_LIMIT_RETRY_EXHAUSTED",
                title="LLM Rate Limit Retries Exhausted",
                intent="Gemini remained rate-limited after configured retry attempts.",
                resolution=(
                    "Increase `LLM_RATE_LIMIT_MAX_RETRIES` (use 0 for unlimited) or wait and rerun. "
                    "You can also increase retry wait settings in `.env`."
                ),
                technical=msg,
            )
        if "outside configured limits" in lower or "must be a string" in lower:
            return CliError(
                code="LLM_CONSTRAINT_MISMATCH",
                title="Generated Text Constraints Not Met",
                intent="LLM response does not satisfy configured field character constraints.",
                resolution="Adjust *_MIN_CHARS/*_MAX_CHARS/FIELD_CHAR_TOLERANCE in `.env` or rerun to regenerate compliant text.",
                technical=msg,
            )
        if "failed to parse llm output" in lower:
            return CliError(
                code="LLM_OUTPUT_INVALID",
                title="Invalid LLM Response",
                intent="LLM response format is not valid diary JSON.",
                resolution="Retry with a clearer task summary. If repeated, regenerate once and continue.",
                technical=msg,
            )
        if any(token in lower for token in ["api key", "unauthorized", "permission", "quota", "rate", "429"]):
            return CliError(
                code="LLM_AUTH_OR_QUOTA",
                title="LLM Access Failed",
                intent="Gemini request was rejected due to key, permission, or quota.",
                resolution="Check `GEMINI_API_KEY` and quota status, then rerun.",
                technical=msg,
            )
        return CliError(
            code="LLM_REQUEST_FAILED",
            title="Diary Generation Failed",
            intent="Could not generate diary draft from the provided task input.",
            resolution="Retry once. If it persists, check network and Gemini API availability.",
            technical=msg,
        )

    if stage_name == "editor":
        if "not valid json" in lower or "invalid json" in lower:
            return CliError(
                code="EDITOR_INVALID_JSON",
                title="Edited JSON Is Invalid",
                intent="Review file was saved with invalid JSON syntax.",
                resolution="Fix JSON syntax in the editor and rerun submission.",
                technical=msg,
            )
        if "editor executable not found" in lower:
            return CliError(
                code="EDITOR_NOT_FOUND",
                title="Editor Launch Failed",
                intent="Configured local editor could not be launched.",
                resolution="Install the editor or set `EDITOR` env var to a valid executable.",
                technical=msg,
            )
        return CliError(
            code="EDITOR_STEP_FAILED",
            title="Review Step Failed",
            intent="Could not complete local review/edit step.",
            resolution="Check editor availability and filesystem access, then rerun.",
            technical=msg,
        )

    if stage_name == "browser":
        if "date was clicked but form did not accept it" in lower:
            return CliError(
                code="BROWSER_DATE_REJECTED",
                title="Date Not Accepted",
                intent="Website rejected the selected diary date.",
                resolution="Choose another valid diary date for the selected internship and rerun.",
                technical=msg,
            )
        if any(token in lower for token in ["could not select month", "could not select year", "datepicker"]):
            return CliError(
                code="BROWSER_DATEPICKER_FAILED",
                title="Datepicker Automation Failed",
                intent="Could not operate month/year/day controls in the date picker.",
                resolution="Keep the diary page visible, avoid manual interaction during run, and retry.",
                technical=msg,
            )
        if "timeout" in lower:
            return CliError(
                code="BROWSER_TIMEOUT",
                title="Browser Step Timed Out",
                intent="Automation waited too long for a required UI state.",
                resolution="Retry once. If repeated, check internet speed and platform responsiveness.",
                technical=msg,
            )
        return CliError(
            code="BROWSER_AUTOMATION_FAILED",
            title="Browser Automation Failed",
            intent="Could not complete browser automation flow.",
            resolution="Rerun and keep browser in foreground. If repeated, share latest logs for selector update.",
            technical=msg,
        )

    if stage_name == "bulk":
        if "bulk csv file not found" in lower:
            return CliError(
                code="BULK_CSV_NOT_FOUND",
                title="Bulk CSV Not Found",
                intent="Bulk mode could not find the requested CSV file.",
                resolution="Create the CSV in project root or pass `--csv-file <path>`.",
                technical=msg,
            )
        if "missing required headers" in lower:
            return CliError(
                code="BULK_CSV_HEADERS_INVALID",
                title="Bulk CSV Headers Invalid",
                intent="Bulk CSV headers do not match expected schema.",
                resolution="Use exactly these CSV headers: `date,description`.",
                technical=msg,
            )
        if "requires --bulk" in lower or "require --bulk" in lower:
            return CliError(
                code="BULK_FLAG_USAGE_INVALID",
                title="Bulk Flag Usage Invalid",
                intent="Bulk-only flags were provided without enabling bulk mode.",
                resolution=(
                    "Use `--bulk` when passing `--resume`, `--csv-file`, `--results-file`, "
                    "`--artifacts-dir`, or `--no-screenshot-on-failure`."
                ),
                technical=msg,
                exit_code=2,
            )
        return CliError(
            code="BULK_RUN_FAILED",
            title="Bulk Run Failed",
            intent="Bulk execution could not be completed.",
            resolution="Check CSV format, retry settings, and row-level logs, then rerun.",
            technical=msg,
        )

    return CliError(
        code="UNEXPECTED_FAILURE",
        title="Unexpected Failure",
        intent="An unhandled runtime error interrupted the flow.",
        resolution="Rerun once. If it persists, share the technical details from this error panel.",
        technical=msg,
    )
