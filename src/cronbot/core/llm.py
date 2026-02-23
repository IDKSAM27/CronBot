import json
import random
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

    def generate_entry(
        self,
        short_text: str,
        compulsory_skills: List[str],
        field_char_limits: FieldCharLimits,
        char_tolerance: int = 40,
    ) -> Dict[str, Any]:
        """Queries Gemini and returns the compiled JSON payload."""
        prompt = self._build_prompt(short_text, field_char_limits)
        
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt
        )
        
        try:
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
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse LLM output: {response.text}") from e
