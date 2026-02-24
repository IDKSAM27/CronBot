import json
import random
import time
from typing import Dict, Any, List

from google import genai

FieldCharLimits = Dict[str, Dict[str, int]]


class LLMGenerator:
    """Handles interaction with the Gemini API to generate diary content."""
    
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.5-flash' 

    def _build_prompt(self, short_text: str, field_char_limits: FieldCharLimits) -> str:
        work_summary_limits = field_char_limits["work_summary"]
        learnings_limits = field_char_limits["learnings"]
        blockers_limits = field_char_limits["blockers"]

        return f"""
        Act as a CS student filling out a daily internship diary.
        Base the entry on this short input: "{short_text}"
        
        Output ONLY a raw JSON object (no markdown, no backticks) with these exact keys and constraints:
        - "work_summary": (String, {work_summary_limits["min"]} to {work_summary_limits["max"]} characters) A professional description of the task.
        - "learnings": (String, {learnings_limits["min"]} to {learnings_limits["max"]} characters) Technical or soft skills improved.
        - "blockers": (String, {blockers_limits["min"]} to {blockers_limits["max"]} characters) Challenges faced, or "None, development proceeded smoothly."
        - "skills": (List of Strings) 1 to 3 technical skills specifically relevant to the input.

        Important:
        - Count characters before final answer.
        - Keep each field concise and within the requested range.
        - If text becomes too long, rewrite it shorter instead of adding extra detail.
        """

    def _is_retryable_rate_limit_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        tokens = [
            "429",
            "rate limit",
            "resource_exhausted",
            "too many requests",
            "quota",
            "exhausted",
        ]
        if any(token in text for token in tokens):
            return True

        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return True

        response = getattr(exc, "response", None)
        if response is not None:
            code = getattr(response, "status_code", None)
            if code == 429:
                return True

        return False

    def _extract_retry_after_seconds(self, exc: Exception) -> int | None:
        """Attempts to read Retry-After from common exception response shapes."""
        candidates: list[str] = []

        response = getattr(exc, "response", None)
        if response is not None:
            headers = getattr(response, "headers", None)
            if headers is not None:
                retry_after = None
                try:
                    retry_after = headers.get("retry-after")
                except Exception:
                    pass
                if retry_after is not None:
                    candidates.append(str(retry_after))

        for raw in candidates:
            raw_clean = raw.strip()
            if raw_clean.isdigit():
                return int(raw_clean)

        return None

    def _apply_backoff_wait(
        self,
        attempt_number: int,
        base_seconds: int,
        max_wait_seconds: int,
        retry_after_seconds: int | None = None,
    ) -> int:
        if retry_after_seconds is not None and retry_after_seconds > 0:
            wait_seconds = retry_after_seconds
        else:
            wait_seconds = min(max_wait_seconds, base_seconds * (2 ** max(0, attempt_number - 1)))
            jitter_cap = max(1, min(8, int(wait_seconds * 0.2)))
            wait_seconds = min(max_wait_seconds, wait_seconds + random.randint(0, jitter_cap))

        time.sleep(max(1, wait_seconds))
        return max(1, wait_seconds)

    def _trim_to_max_chars(self, text: str, max_chars: int) -> str:
        """Trims long text to max chars while preferring sentence boundaries."""
        normalized = " ".join(text.split()).strip()
        if len(normalized) <= max_chars:
            return normalized

        candidate = normalized[:max_chars].rstrip()
        last_break = max(candidate.rfind("."), candidate.rfind("!"), candidate.rfind("?"), candidate.rfind(";"))
        if last_break >= int(max_chars * 0.6):
            candidate = candidate[: last_break + 1].strip()
        return candidate

    def _apply_length_policy(
        self,
        data: Dict[str, Any],
        field_char_limits: FieldCharLimits,
        tolerance: int,
    ) -> list[str]:
        warnings: list[str] = []

        for field_name, bounds in field_char_limits.items():
            value = data.get(field_name)
            if not isinstance(value, str):
                raise ValueError(f"LLM output field '{field_name}' must be a string.")

            normalized = " ".join(value.split()).strip()
            char_count = len(normalized)
            min_chars = bounds["min"]
            max_chars = bounds["max"]
            soft_min = max(1, min_chars - tolerance)
            soft_max = max_chars + tolerance

            if char_count > soft_max:
                trimmed = self._trim_to_max_chars(normalized, max_chars)
                trimmed_len = len(trimmed)
                data[field_name] = trimmed
                warnings.append(
                    f"{field_name} trimmed from {char_count} to {trimmed_len} chars (max {max_chars}, tolerance {tolerance})."
                )
                char_count = trimmed_len
            else:
                data[field_name] = normalized
                if char_count > max_chars:
                    warnings.append(
                        f"{field_name} is {char_count} chars (max {max_chars}, accepted via tolerance +{tolerance})."
                    )

            if char_count < soft_min:
                raise ValueError(
                    f"Field '{field_name}' length {char_count} is outside configured limits "
                    f"{min_chars}-{max_chars} (tolerance {tolerance})."
                )

            if char_count < min_chars:
                warnings.append(
                    f"{field_name} is {char_count} chars (min {min_chars}, accepted via tolerance -{tolerance})."
                )

        return warnings

    def _generate_entry_once(
        self,
        short_text: str,
        compulsory_skills: List[str],
        field_char_limits: FieldCharLimits,
        char_tolerance: int,
    ) -> Dict[str, Any]:
        prompt = self._build_prompt(short_text, field_char_limits)

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt
        )

        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        length_warnings = self._apply_length_policy(data, field_char_limits, char_tolerance)

        data["hours"] = str(random.choice([7.0, 7.25, 7.5, 7.75, 8.0, 8.25, 8.5, 8.75, 9.0]))

        llm_skills = data.get('skills', [])

        # Merge with compulsory, keeping compulsory first, removing duplicates
        final_skills = compulsory_skills.copy()
        for s in llm_skills:
            if s not in final_skills:
                final_skills.append(s)

        data["skills"] = final_skills
        if length_warnings:
            data["_generation_warnings"] = length_warnings

        return data

    def generate_entry(
        self,
        short_text: str,
        compulsory_skills: List[str],
        field_char_limits: FieldCharLimits,
        char_tolerance: int = 40,
        retry_base_seconds: int = 8,
        retry_max_wait_seconds: int = 300,
        rate_limit_max_retries: int = 0,
        on_retry=None,
    ) -> Dict[str, Any]:
        """Queries Gemini and returns the compiled JSON payload."""
        attempt = 0
        while True:
            attempt += 1
            try:
                return self._generate_entry_once(
                    short_text=short_text,
                    compulsory_skills=compulsory_skills,
                    field_char_limits=field_char_limits,
                    char_tolerance=char_tolerance,
                )
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse LLM output: {e}") from e
            except Exception as e:
                if not self._is_retryable_rate_limit_error(e):
                    raise

                if rate_limit_max_retries > 0 and attempt > rate_limit_max_retries:
                    raise RuntimeError(
                        f"Gemini rate limit retries exhausted after {rate_limit_max_retries} attempts."
                    ) from e

                retry_after_seconds = self._extract_retry_after_seconds(e)
                wait_seconds = self._apply_backoff_wait(
                    attempt_number=attempt,
                    base_seconds=retry_base_seconds,
                    max_wait_seconds=retry_max_wait_seconds,
                    retry_after_seconds=retry_after_seconds,
                )
                if on_retry:
                    on_retry(attempt, wait_seconds, str(e))
