from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from playwright.sync_api import sync_playwright
from rich.status import Status

_SRC_DIR = os.path.join(os.path.dirname(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from cronbot.automation.browser import DiaryAutomator
from cronbot.cli import ui
from cronbot.config import load_config
from cronbot.core.bulk import BulkFileLogger, BulkResultStore, load_bulk_csv, make_safe_filename_fragment
from cronbot.core.editor import interactive_edit
from cronbot.core.llm import LLMGenerator
from cronbot.exceptions import to_cli_error

app = typer.Typer(help="Internship Diary Automation CLI", no_args_is_help=True)


class BulkFlagUsageError(ValueError):
    """Raised when bulk-only flags are used without --bulk."""



def _normalize_legacy_cli_flags() -> None:
    """Normalizes legacy single-dash long flags for compatibility."""
    normalized_args: list[str] = []
    for arg in sys.argv[1:]:
        if arg.lower() == "-force":
            normalized_args.append("--force")
        else:
            normalized_args.append(arg)
    sys.argv = [sys.argv[0], *normalized_args]



def _exit_with_stage_error(stage: str, exc: Exception) -> None:
    error = to_cli_error(exc, stage)
    ui.print_cli_error(error)
    raise typer.Exit(code=error.exit_code)



def _short_text(value: str, limit: int = 140) -> str:
    condensed = " ".join(value.split())
    if len(condensed) <= limit:
        return condensed
    return f"{condensed[:limit - 3]}..."



def _build_llm_retry_callback(label: str, file_logger: BulkFileLogger | None = None):
    def _on_retry(attempt: int, wait_seconds: int, reason: str):
        message = f"{label}: Gemini rate limit detected, retry {attempt} in {wait_seconds}s."
        ui.print_warning(message)
        ui.print_substep(f"Retry reason: {_short_text(reason, limit=220)}")
        if file_logger is not None:
            file_logger.warn(f"{message} Reason={_short_text(reason, limit=360)}")

    return _on_retry



def _generate_entry_with_policy(
    llm: LLMGenerator,
    config: dict[str, Any],
    task_input: str,
    on_retry=None,
) -> dict[str, Any]:
    return llm.generate_entry(
        task_input,
        config["COMPULSORY_SKILLS"],
        config["FIELD_CHAR_LIMITS"],
        config["FIELD_CHAR_TOLERANCE"],
        retry_base_seconds=config["LLM_RATE_LIMIT_RETRY_BASE_SECONDS"],
        retry_max_wait_seconds=config["LLM_RATE_LIMIT_RETRY_MAX_WAIT_SECONDS"],
        rate_limit_max_retries=config["LLM_RATE_LIMIT_MAX_RETRIES"],
        on_retry=on_retry,
    )



def _run_single_submission(config: dict[str, Any]) -> None:
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
            entry_data = _generate_entry_with_policy(
                llm,
                config,
                raw_task,
                on_retry=_build_llm_retry_callback("Single run"),
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



def _run_bulk_submission(
    config: dict[str, Any],
    csv_file: Path,
    force: bool,
    resume: bool,
    results_file: Path,
    artifacts_dir: Path,
    screenshot_on_failure: bool,
) -> None:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = csv_file.expanduser().resolve()
    results_path = results_file.expanduser().resolve()
    artifacts_root = artifacts_dir.expanduser().resolve()
    run_log_path = artifacts_root / f"bulk_run_{run_id}.log"
    screenshot_dir = artifacts_root / "screenshots" / run_id

    file_logger = BulkFileLogger(run_log_path)
    result_store = BulkResultStore(results_path)

    ui.print_step("Bulk mode enabled.")
    ui.print_substep(f"Mode: {'force' if force else 'interactive'}")
    ui.print_substep(f"CSV input: {csv_path}")
    ui.print_substep(f"Results CSV: {results_path}")
    ui.print_substep(f"Run log: {run_log_path}")

    file_logger.info(f"Bulk run started. run_id={run_id} mode={'force' if force else 'interactive'}")
    file_logger.info(f"CSV input={csv_path}")
    file_logger.info(f"Results file={results_path}")

    try:
        loaded = load_bulk_csv(csv_path)
    except Exception as e:
        _exit_with_stage_error("bulk", e)

    if not loaded.rows and not loaded.rejected_rows:
        _exit_with_stage_error("bulk", ValueError("Bulk CSV has no rows."))

    rejected_count = 0
    for rejected in loaded.rejected_rows:
        rejected_count += 1
        reason = (
            f"Skipping invalid CSV row {rejected.row_number}: {rejected.reason} "
            f"(date='{rejected.date}', description='{_short_text(rejected.description, 70)}')"
        )
        ui.print_warning(reason)
        file_logger.warn(reason)

        now = datetime.now().isoformat(timespec="seconds")
        result_store.append(
            {
                "run_id": run_id,
                "row_index": "",
                "csv_row": rejected.row_number,
                "date": rejected.date,
                "description": rejected.description,
                "status": "invalid_csv_row",
                "mode": "force" if force else "interactive",
                "error_code": "BULK_CSV_ROW_INVALID",
                "error_message": rejected.reason,
                "retries": 0,
                "retry_wait_seconds": 0,
                "screenshot": "",
                "started_at": now,
                "ended_at": now,
                "duration_seconds": "0.00",
            }
        )

    if not loaded.rows:
        _exit_with_stage_error("bulk", ValueError("Bulk CSV has no valid rows after validation."))

    completed_signatures: set[str] = set()
    if resume:
        completed_signatures = result_store.load_success_signatures()
        ui.print_substep(f"Resume enabled: {len(completed_signatures)} successful rows detected from history.")
        file_logger.info(f"Resume mode enabled. found_success_signatures={len(completed_signatures)}")

    ui.print_step(
        f"Bulk queue prepared: {len(loaded.rows)} valid rows, {rejected_count} invalid rows."
    )

    try:
        llm = LLMGenerator(config["GEMINI_KEY"])
    except Exception as e:
        _exit_with_stage_error("llm", e)

    success_count = 0
    failed_count = 0
    skipped_resume_count = 0

    with sync_playwright() as p:
        bot = None

        def log_step(message: str):
            ui.print_substep(message)
            file_logger.info(f"[browser] {message}")

        try:
            bot = DiaryAutomator(p, config, log_step)
            bot.authenticate_and_navigate()

            total_rows = len(loaded.rows)
            for row_index, row in enumerate(loaded.rows, start=1):
                if resume and row.signature in completed_signatures:
                    skipped_resume_count += 1
                    ui.print_step(
                        f"[{row_index}/{total_rows}] Skipping already successful row from history: {row.date}"
                    )
                    file_logger.info(
                        f"Row skipped by resume. row_index={row_index} csv_row={row.row_number} date={row.date}"
                    )

                    now = datetime.now().isoformat(timespec="seconds")
                    result_store.append(
                        {
                            "run_id": run_id,
                            "row_index": row_index,
                            "csv_row": row.row_number,
                            "date": row.date,
                            "description": row.description,
                            "status": "skipped_resume",
                            "mode": "force" if force else "interactive",
                            "error_code": "",
                            "error_message": "already successful in previous run",
                            "retries": 0,
                            "retry_wait_seconds": 0,
                            "screenshot": "",
                            "started_at": now,
                            "ended_at": now,
                            "duration_seconds": "0.00",
                        }
                    )
                    continue

                started_at = datetime.now()
                stage = "bulk"
                screenshot_path = ""
                error_code = ""
                error_message = ""
                retry_count = 0
                retry_wait_seconds = 0
                status = "success"

                ui.print_step(
                    f"[{row_index}/{total_rows}] Processing CSV row {row.row_number} for date {row.date}."
                )
                ui.print_substep(f"Task summary: {_short_text(row.description, 140)}")
                file_logger.info(
                    f"Row start. row_index={row_index} csv_row={row.row_number} date={row.date}"
                )

                try:
                    stage = "llm"

                    def on_retry(attempt: int, wait_seconds: int, reason: str):
                        nonlocal retry_count
                        nonlocal retry_wait_seconds
                        retry_count = attempt
                        retry_wait_seconds += wait_seconds
                        callback = _build_llm_retry_callback(
                            label=(f"Row {row_index}/{total_rows}"),
                            file_logger=file_logger,
                        )
                        callback(attempt, wait_seconds, reason)

                    with Status(
                        f"[step]Generating row {row_index}/{total_rows}...[/step]",
                        spinner="dots12",
                        console=ui.console,
                    ):
                        entry_data = _generate_entry_with_policy(
                            llm,
                            config,
                            row.description,
                            on_retry=on_retry,
                        )

                    generation_warnings = entry_data.pop("_generation_warnings", [])
                    for warning in generation_warnings:
                        ui.print_warning(f"Row {row_index}: LLM length policy: {warning}")
                        file_logger.warn(f"Row {row_index} length warning: {warning}")

                    if not force:
                        ui.print_entry_preview(entry_data, f"LLM Draft {row_index}/{total_rows}")
                        ui.print_step(f"[{row_index}/{total_rows}] Opening editor review.")
                        ui.print_editor_intro()
                        stage = "editor"
                        final_data = interactive_edit(entry_data)
                        ui.print_entry_preview(final_data, f"Reviewed Payload {row_index}/{total_rows}")
                    else:
                        final_data = entry_data
                        ui.print_substep("Force mode enabled: skipping JSON editor review.")

                    stage = "browser"
                    bot.open_diary_page()
                    bot.fill_initial_selection(row.date)
                    bot.fill_and_submit_diary(final_data)

                    if force:
                        ui.print_substep("Force mode enabled: auto-clicking Save.")
                        bot.click_save_button()
                    else:
                        ui.print_step(f"[{row_index}/{total_rows}] Waiting for save confirmation.")
                        ui.print_save_gate()
                        bot.wait_for_user_to_save(ui.check_cli_save_input)

                    success_count += 1
                    if resume:
                        completed_signatures.add(row.signature)

                    ui.print_success(f"[{row_index}/{total_rows}] Entry submitted for {row.date}.")
                    file_logger.info(
                        f"Row success. row_index={row_index} csv_row={row.row_number} date={row.date}"
                    )
                except Exception as e:
                    status = "failed"
                    failed_count += 1
                    cli_error = to_cli_error(e, stage)
                    error_code = cli_error.code
                    technical = cli_error.technical if cli_error.technical else str(e)
                    error_message = f"{cli_error.intent} | {_short_text(technical, 320)}"

                    ui.print_cli_error(cli_error)
                    file_logger.error(
                        "Row failed. "
                        f"row_index={row_index} csv_row={row.row_number} stage={stage} "
                        f"code={cli_error.code} message={_short_text(technical, 400)}"
                    )

                    if screenshot_on_failure and stage == "browser" and bot is not None:
                        screenshot_name = (
                            f"row_{row_index:04d}_csv_{row.row_number:04d}_"
                            f"{make_safe_filename_fragment(row.date)}.png"
                        )
                        screenshot_target = screenshot_dir / screenshot_name
                        try:
                            bot.capture_screenshot(screenshot_target)
                            screenshot_path = str(screenshot_target)
                            file_logger.info(
                                f"Failure screenshot captured for row {row_index}: {screenshot_path}"
                            )
                        except Exception as screenshot_error:
                            file_logger.warn(
                                f"Failed to capture screenshot for row {row_index}: {screenshot_error}"
                            )
                finally:
                    ended_at = datetime.now()
                    duration_seconds = (ended_at - started_at).total_seconds()
                    result_store.append(
                        {
                            "run_id": run_id,
                            "row_index": row_index,
                            "csv_row": row.row_number,
                            "date": row.date,
                            "description": row.description,
                            "status": status,
                            "mode": "force" if force else "interactive",
                            "error_code": error_code,
                            "error_message": error_message,
                            "retries": retry_count,
                            "retry_wait_seconds": retry_wait_seconds,
                            "screenshot": screenshot_path,
                            "started_at": started_at.isoformat(timespec="seconds"),
                            "ended_at": ended_at.isoformat(timespec="seconds"),
                            "duration_seconds": f"{duration_seconds:.2f}",
                        }
                    )
        finally:
            if bot is not None:
                bot.close()

    processed_count = len(loaded.rows)
    skipped_total = rejected_count + skipped_resume_count

    ui.print_step("Bulk run finished.")
    ui.print_substep(f"Run ID: {run_id}")
    ui.print_substep(f"Processed rows: {processed_count}")
    ui.print_substep(f"Succeeded: {success_count}")
    ui.print_substep(f"Failed: {failed_count}")
    ui.print_substep(f"Skipped: {skipped_total} (invalid={rejected_count}, resume={skipped_resume_count})")
    ui.print_substep(f"Results CSV: {results_path}")
    ui.print_substep(f"Detailed log: {run_log_path}")

    file_logger.info(
        "Bulk run complete. "
        f"run_id={run_id} processed={processed_count} success={success_count} "
        f"failed={failed_count} skipped_invalid={rejected_count} skipped_resume={skipped_resume_count}"
    )

    if failed_count > 0:
        raise typer.Exit(code=1)


@app.command()
def submit(
    theme: str = typer.Option(
        "claude",
        "--theme",
        "-t",
        help=f"CLI theme ({', '.join(ui.theme_names())})",
        show_default=True,
    ),
    bulk: bool = typer.Option(
        False,
        "--bulk",
        help="Run in CSV bulk mode (reads date/description rows).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Bulk mode only: skip editor/save confirmation and auto-submit each row.",
    ),
    csv_file: Path = typer.Option(
        Path("bulk.csv"),
        "--csv-file",
        help="Bulk mode only: CSV path with headers date,description.",
        show_default=True,
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        help="Bulk mode only: skip rows already marked success in results CSV.",
    ),
    results_file: Path = typer.Option(
        Path("bulk_results.csv"),
        "--results-file",
        help="Bulk mode only: output CSV for row-by-row status.",
        show_default=True,
    ),
    artifacts_dir: Path = typer.Option(
        Path("bulk_artifacts"),
        "--artifacts-dir",
        help="Bulk mode only: directory for detailed logs/screenshots.",
        show_default=True,
    ),
    screenshot_on_failure: bool = typer.Option(
        True,
        "--screenshot-on-failure/--no-screenshot-on-failure",
        help="Bulk mode only: capture screenshot for browser-stage failures.",
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

    bulk_flags_used = (
        force
        or resume
        or csv_file != Path("bulk.csv")
        or results_file != Path("bulk_results.csv")
        or artifacts_dir != Path("bulk_artifacts")
        or not screenshot_on_failure
    )
    if bulk_flags_used and not bulk:
        _exit_with_stage_error(
            "bulk",
            BulkFlagUsageError("Bulk-only flags require --bulk."),
        )

    if bulk:
        _run_bulk_submission(
            config=config,
            csv_file=csv_file,
            force=force,
            resume=resume,
            results_file=results_file,
            artifacts_dir=artifacts_dir,
            screenshot_on_failure=screenshot_on_failure,
        )
        return

    _run_single_submission(config)



def run_cli() -> None:
    _normalize_legacy_cli_flags()
    app()


if __name__ == "__main__":
    run_cli()
