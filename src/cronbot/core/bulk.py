from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class BulkCsvRow:
    """One valid row parsed from bulk CSV input."""

    row_number: int
    date: str
    description: str

    @property
    def signature(self) -> str:
        normalized_desc = " ".join(self.description.split()).strip().lower()
        return f"{self.date}|{normalized_desc}"


@dataclass(slots=True)
class BulkRejectedRow:
    """One rejected CSV row with rejection reason."""

    row_number: int
    date: str
    description: str
    reason: str


@dataclass(slots=True)
class BulkCsvLoadResult:
    """Parsed bulk rows with invalid row diagnostics."""

    rows: list[BulkCsvRow]
    rejected_rows: list[BulkRejectedRow]


def _normalize_header_map(fieldnames: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for name in fieldnames:
        key = name.strip().lower()
        if key and key not in mapping:
            mapping[key] = name
    return mapping


def _is_valid_ddmmyyyy(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
        return True
    except ValueError:
        return False


def load_bulk_csv(csv_path: Path) -> BulkCsvLoadResult:
    """Loads and validates bulk CSV input."""
    path = csv_path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Bulk CSV file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Bulk CSV path is not a file: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("Bulk CSV is missing header row. Required headers: date, description.")

        header_map = _normalize_header_map([name for name in reader.fieldnames if name is not None])
        missing_headers = [name for name in ("date", "description") if name not in header_map]
        if missing_headers:
            raise ValueError(
                "Bulk CSV is missing required headers: "
                f"{', '.join(missing_headers)}. Expected headers: date, description."
            )

        date_header = header_map["date"]
        desc_header = header_map["description"]

        valid_rows: list[BulkCsvRow] = []
        rejected_rows: list[BulkRejectedRow] = []

        for row_number, raw_row in enumerate(reader, start=2):
            raw_date = (raw_row.get(date_header) or "").strip()
            raw_desc = (raw_row.get(desc_header) or "").strip()

            if not raw_date:
                rejected_rows.append(
                    BulkRejectedRow(
                        row_number=row_number,
                        date="",
                        description=raw_desc,
                        reason="date is empty",
                    )
                )
                continue

            if not _is_valid_ddmmyyyy(raw_date):
                rejected_rows.append(
                    BulkRejectedRow(
                        row_number=row_number,
                        date=raw_date,
                        description=raw_desc,
                        reason="date must be in DD-MM-YYYY format",
                    )
                )
                continue

            if not raw_desc:
                rejected_rows.append(
                    BulkRejectedRow(
                        row_number=row_number,
                        date=raw_date,
                        description="",
                        reason="description is empty",
                    )
                )
                continue

            valid_rows.append(
                BulkCsvRow(
                    row_number=row_number,
                    date=raw_date,
                    description=raw_desc,
                )
            )

    return BulkCsvLoadResult(rows=valid_rows, rejected_rows=rejected_rows)


class BulkFileLogger:
    """Simple file logger for detailed bulk traces."""

    def __init__(self, log_file: Path):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, level: str, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{timestamp} [{level}] {message.rstrip()}\n"
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def info(self, message: str):
        self._write("INFO", message)

    def warn(self, message: str):
        self._write("WARN", message)

    def error(self, message: str):
        self._write("ERROR", message)


def _safe_csv_value(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


class BulkResultStore:
    """Persists row-level outcomes for resume/idempotency and reporting."""

    FIELDNAMES = [
        "run_id",
        "row_index",
        "csv_row",
        "date",
        "description",
        "status",
        "mode",
        "error_code",
        "error_message",
        "retries",
        "retry_wait_seconds",
        "screenshot",
        "started_at",
        "ended_at",
        "duration_seconds",
    ]

    def __init__(self, csv_file: Path):
        self.csv_file = csv_file
        self.csv_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_header()

    def _ensure_header(self):
        if self.csv_file.exists() and self.csv_file.stat().st_size > 0:
            return
        with self.csv_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.FIELDNAMES)
            writer.writeheader()

    def append(self, row: dict[str, Any]):
        serialized = {key: _safe_csv_value(row.get(key, "")) for key in self.FIELDNAMES}
        with self.csv_file.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.FIELDNAMES)
            writer.writerow(serialized)

    def load_success_signatures(self) -> set[str]:
        signatures: set[str] = set()
        if not self.csv_file.exists() or self.csv_file.stat().st_size == 0:
            return signatures

        with self.csv_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                status = (row.get("status") or "").strip().lower()
                if status != "success":
                    continue
                date = (row.get("date") or "").strip()
                desc = (row.get("description") or "").strip()
                if not date or not desc:
                    continue
                normalized_desc = " ".join(desc.split()).strip().lower()
                signatures.add(f"{date}|{normalized_desc}")

        return signatures


def make_safe_filename_fragment(value: str) -> str:
    safe_chars = []
    for char in value:
        if char.isalnum():
            safe_chars.append(char)
        elif char in ("-", "_"):
            safe_chars.append(char)
        else:
            safe_chars.append("_")
    condensed = "".join(safe_chars).strip("_")
    return condensed[:80] if condensed else "item"
