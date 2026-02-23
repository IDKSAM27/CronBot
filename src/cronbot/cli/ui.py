from __future__ import annotations

import platform
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

if TYPE_CHECKING:
    from cronbot.exceptions import CliError

_THEME_PRESETS: dict[str, dict[str, str]] = {
    "claude": {
        "brand": "bold #EBCB8B",
        "border": "#7F6A3C",
        "step": "bold #89B4FA",
        "ok": "bold #A6E3A1",
        "warn": "bold #F9E2AF",
        "error": "bold #F38BA8",
        "muted": "#7D8694",
        "label": "bold #BAC2DE",
        "value": "#CDD6F4",
        "log": "#A6ADC8",
        "hint": "#94E2D5",
        "accent": "#F5C2E7",
    },
    "clean": {
        "brand": "bold #6DC7F2",
        "border": "#3D7D99",
        "step": "bold #8ED2A8",
        "ok": "bold #8ED2A8",
        "warn": "bold #F2CC8F",
        "error": "bold #E07A5F",
        "muted": "#7A8593",
        "label": "bold #A8DADC",
        "value": "#F1FAEE",
        "log": "#C6D6DF",
        "hint": "#F2CC8F",
        "accent": "#BDE0FE",
    },
}


def _build_console(theme_name: str) -> Console:
    return Console(theme=Theme(_THEME_PRESETS[theme_name]), highlight=False, soft_wrap=True)


_current_theme_name = "claude"
_step_counter = 0
console = _build_console(_current_theme_name)
_LABEL_COLUMN_WIDTH = 12


def _label_value_table() -> Table:
    """Creates a consistent two-column label/value table for panel content."""
    table = Table.grid(padding=(0, 1))
    table.add_column(
        style="label",
        justify="left",
        no_wrap=True,
        width=_LABEL_COLUMN_WIDTH,
    )
    table.add_column(style="value")
    return table


def theme_names() -> tuple[str, ...]:
    """Returns allowed theme names."""
    return tuple(sorted(_THEME_PRESETS.keys()))


def set_theme(theme_name: str) -> str:
    """Switches the global UI theme."""
    normalized = theme_name.strip().lower()
    if normalized not in _THEME_PRESETS:
        options = ", ".join(theme_names())
        raise ValueError(f"Unknown theme '{theme_name}'. Available themes: {options}.")

    global console
    global _current_theme_name
    console = _build_console(normalized)
    _current_theme_name = normalized
    return _current_theme_name


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _is_valid_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%d-%m-%Y")
        return True
    except ValueError:
        return False


def _preview_value(value: Any, limit: int = 90) -> str:
    if isinstance(value, list):
        raw = ", ".join(str(item) for item in value)
    else:
        raw = str(value)

    condensed = " ".join(raw.split())
    if len(condensed) <= limit:
        return condensed
    return f"{condensed[:limit - 3]}..."


def print_header():
    """Prints a themed session header."""
    global _step_counter
    _step_counter = 0

    table = _label_value_table()
    table.add_row("Mode", "Internship diary automation with human review")
    table.add_row("Flow", "Draft -> JSON edit -> Browser fill -> Save")
    table.add_row("Shortcut", "Press y or Enter in CLI to trigger Save")

    console.print()
    console.print(
        Panel(
            table,
            title="[brand]CRONBOT CLI[/brand]",
            subtitle=f"[muted]{datetime.now().strftime('%a %d %b %Y %H:%M')}[/muted]",
            border_style="border",
            box=box.ASCII,
        )
    )
    console.print()


def print_run_summary(
    target_date: str,
    raw_task: str,
    compulsory_skills: list[str],
    field_char_limits: dict[str, dict[str, int]] | None = None,
    field_char_tolerance: int | None = None,
):
    """Prints a compact summary of input values before generation."""
    table = _label_value_table()
    table.add_row("Target date", target_date)
    table.add_row("Task input", _preview_value(raw_task, limit=110))
    table.add_row("Forced skills", _preview_value(compulsory_skills, limit=110))

    if field_char_limits:
        rows = []
        for key in ("work_summary", "learnings", "blockers"):
            if key not in field_char_limits:
                continue
            bounds = field_char_limits[key]
            rows.append(f"{key}={bounds['min']}-{bounds['max']}")
        if rows:
            char_line = ", ".join(rows)
            if field_char_tolerance is not None:
                char_line = f"{char_line} (tolerance +/-{field_char_tolerance})"
            table.add_row("Char limits", char_line)

    console.print(
        Panel(
            table,
            title="[accent]Session Input[/accent]",
            border_style="border",
            box=box.ASCII,
        )
    )


def print_entry_preview(data: dict[str, Any], title: str):
    """Prints a quick structured preview of generated diary payload."""
    fields: list[tuple[str, str]] = [
        ("work_summary", "Work summary"),
        ("hours", "Hours"),
        ("learnings", "Learnings"),
        ("blockers", "Blockers"),
        ("skills", "Skills"),
    ]

    table = Table(show_header=True, header_style="label", box=box.ASCII, expand=True)
    table.add_column("Field", style="label", no_wrap=True)
    table.add_column("Preview", style="value")
    table.add_column("Chars", style="muted", justify="right", width=7)

    for key, label in fields:
        if key not in data:
            continue
        value = data[key]
        char_count = len(", ".join(value)) if isinstance(value, list) else len(str(value))
        table.add_row(label, _preview_value(value), str(char_count))

    console.print(
        Panel(
            table,
            title=f"[accent]{title}[/accent]",
            border_style="border",
            box=box.ASCII,
        )
    )


def print_editor_intro():
    """Guides the user before opening the external editor."""
    console.print(
        Panel(
            "Review generated JSON in your editor.\nSave and close the file to continue the automation.",
            title="[hint]Human Review[/hint]",
            border_style="border",
            box=box.ASCII,
        )
    )


def print_save_gate():
    """Shows save options once browser form is filled."""
    console.print(
        Panel(
            "Browser is waiting for final confirmation.\n"
            "- Click Save in the browser\n"
            "- Or press y / Enter here to auto-click Save",
            title="[hint]Save Gate[/hint]",
            border_style="border",
            box=box.ASCII,
        )
    )


def print_error(msg: str):
    """Prints a clear error message."""
    console.print(f"[error]ERROR[/error] {msg}")


def print_cli_error(err: "CliError"):
    """Prints a structured error intent panel."""
    table = _label_value_table()
    table.add_row("Intent", err.intent)
    table.add_row("Action", err.resolution)
    if err.technical:
        table.add_row("Details", _preview_value(err.technical, limit=220))

    console.print(
        Panel(
            table,
            title=f"[error]{err.title}[/error] [muted]{err.code}[/muted]",
            border_style="error",
            box=box.ASCII,
        )
    )


def print_success(msg: str):
    """Prints a success message."""
    console.print(f"[ok]OK[/ok] {msg}")


def print_warning(msg: str):
    """Prints a warning message."""
    console.print(f"[warn]WARN[/warn] {msg}")


def print_info(msg: str):
    """Prints neutral informational text."""
    console.print(f"[accent]INFO[/accent] {msg}")


def print_step(msg: str):
    """Prints a numbered progress step."""
    global _step_counter
    _step_counter += 1
    console.print(f"[muted]{_timestamp()}[/muted] [step]{_step_counter:02d}[/step] {msg}")


def print_substep(msg: str):
    """Prints child logs under a broader step."""
    console.print(f"   [muted]|[/muted] [log]{msg}[/log]")


def _input_line(label: str, hint: str | None = None) -> str:
    """Prints a styled label + optional hint and reads one input line."""
    console.print(f"[label]{label}[/label]")
    if hint:
        console.print(f"[muted]{hint}[/muted]")
    return console.input("[accent]>> [/accent]").strip()


def ask_date(default_date: str) -> str:
    """Prompts the user for the target date."""
    console.print(
        Panel(
            f"Select target diary date.\n"
            f"[value]1[/value] Use today [muted]({default_date})[/muted]\n"
            f"[value]2[/value] Enter custom date [muted](DD-MM-YYYY)[/muted]",
            title="[hint]Date Input[/hint]",
            border_style="border",
            box=box.ASCII,
        )
    )

    while True:
        mode = _input_line("Choose option [1/2]", "Press Enter for option 1")
        normalized_mode = mode.lower()
        if normalized_mode in {"", "1", "today", "t", "y", "yes"}:
            return default_date
        if normalized_mode not in {"2", "custom", "c"}:
            print_warning("Please enter 1 for today or 2 for custom.")
            continue

        user_date = _input_line("Enter target date", "Format: DD-MM-YYYY, e.g. 23-02-2026")
        if _is_valid_date(user_date):
            return user_date
        print_warning("Invalid date format. Expected DD-MM-YYYY.")


def ask_task() -> str:
    """Prompts the user for the daily task."""
    console.print(
        Panel(
            "Write one clear line about the most important work done today.\n"
            "Good: Implemented CLI theming and improved date validation flow.\n"
            "Avoid: Worked on code.",
            title="[hint]Task Input[/hint]",
            border_style="border",
            box=box.ASCII,
        )
    )

    while True:
        task = _input_line("Task summary", "One sentence, action + scope").strip()
        if task:
            if len(task) < 12:
                print_warning("Task summary is too short. Add action + scope.")
                continue
            return task
        print_warning("Task summary cannot be empty.")


def check_cli_save_input() -> bool:
    """Non-blocking check if user pressed 'y' or 'Enter'."""
    if platform.system() == "Windows":
        import msvcrt

        if msvcrt.kbhit():
            char = msvcrt.getch()
            try:
                decoded = char.decode("utf-8", errors="ignore").lower()
                if decoded in ["y", "\r", "\n"]:
                    return True
            except Exception:
                pass
    else:
        import select
        import sys

        dr, _, _ = select.select([sys.stdin], [], [], 0.0)
        if dr:
            char = sys.stdin.read(1)
            if char.lower() in ["y", "\n"]:
                return True
    return False
