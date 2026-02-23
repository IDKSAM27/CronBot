from __future__ import annotations

import os
import sys
from datetime import datetime

import typer
from playwright.sync_api import sync_playwright
from rich.status import Status

_SRC_DIR = os.path.join(os.path.dirname(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from cronbot.automation.browser import DiaryAutomator
from cronbot.cli import ui
from cronbot.config import load_config
from cronbot.core.editor import interactive_edit
from cronbot.core.llm import LLMGenerator
from cronbot.exceptions import to_cli_error

app = typer.Typer(help="Internship Diary Automation CLI", no_args_is_help=True)


def _exit_with_stage_error(stage: str, exc: Exception) -> None:
    error = to_cli_error(exc, stage)
    ui.print_cli_error(error)
    raise typer.Exit(code=error.exit_code)


@app.command()
def submit(
    theme: str = typer.Option(
        "claude",
        "--theme",
        "-t",
        help=f"CLI theme ({', '.join(ui.theme_names())})",
        show_default=True,
    ),
):
    """Run the diary submission automation."""
    try:
        ui.set_theme(theme)
    except ValueError as e:
        _exit_with_stage_error("theme", e)

    ui.print_header()

    try:
        config = load_config()
    except Exception as e:
        _exit_with_stage_error("config", e)

    today = datetime.now().strftime("%d-%m-%Y")
    target_date = ui.ask_date(today)
    raw_task = ui.ask_task()
    ui.print_run_summary(
        target_date,
        raw_task,
        config["COMPULSORY_SKILLS"],
        config["FIELD_CHAR_LIMITS"],
        config["FIELD_CHAR_TOLERANCE"],
    )

    ui.print_step("Generating diary entry with Gemini.")
    try:
        llm = LLMGenerator(config["GEMINI_KEY"])
    except Exception as e:
        _exit_with_stage_error("llm", e)

    with Status("[step]Thinking and drafting entry...[/step]", spinner="dots12", console=ui.console):
        try:
            entry_data = llm.generate_entry(
                raw_task,
                config["COMPULSORY_SKILLS"],
                config["FIELD_CHAR_LIMITS"],
                config["FIELD_CHAR_TOLERANCE"],
            )
        except Exception as e:
            _exit_with_stage_error("llm", e)

    generation_warnings = entry_data.pop("_generation_warnings", [])
    for warning in generation_warnings:
        ui.print_warning(f"LLM length policy: {warning}")

    ui.print_success("Draft generated.")
    ui.print_entry_preview(entry_data, "LLM Draft")

    ui.print_step("Opening local editor for your review.")
    ui.print_editor_intro()
    try:
        final_data = interactive_edit(entry_data)
    except Exception as e:
        _exit_with_stage_error("editor", e)

    ui.print_entry_preview(final_data, "Reviewed Payload")

    ui.print_step("Initializing browser automation.")
    with sync_playwright() as p:
        bot = None

        def log_step(msg: str):
            ui.print_substep(msg)

        try:
            bot = DiaryAutomator(p, config, log_step)
            bot.authenticate_and_navigate()
            bot.fill_initial_selection(target_date)
            bot.fill_and_submit_diary(final_data)
            ui.print_step("Waiting for save confirmation.")
            ui.print_save_gate()
            bot.wait_for_user_to_save(ui.check_cli_save_input)
            ui.print_success("Diary entry submitted successfully.")
        except Exception as e:
            _exit_with_stage_error("browser", e)
        finally:
            if bot is not None:
                bot.close()


if __name__ == "__main__":
    app()
