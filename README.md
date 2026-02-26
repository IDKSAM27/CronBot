# Cronbot CLI

Cronbot automates internship diary entry with human-in-the-loop by default and force mode for fast submission.

1. Generate a draft from your short task summary (Gemini)
2. Open JSON in a local editor for manual review
3. Fill the diary form in a real browser (Playwright)
4. Save from browser, or press `y` / `Enter` in CLI to auto-click Save

It is designed to reduce repetitive form filling while keeping final user control.

## Features

- Themed terminal UI (`claude`, `clean`)
- Structured error panels with intent and fix action
- Datepicker automation with month/year/day handling
- Browser login session reuse via `browser_state.json`
- Field-level character limits from `.env`
- Single-run force mode with `-f` / `--force` (`-force` alias supported)
- Bulk CSV mode with `--bulk` (interactive) and `--bulk --force` (auto-submit)
- Resume/idempotency support with row-level result history
- Detailed run logs and optional failure screenshots for browser-stage failures

## Requirements

- Python `3.11+`
- Internet access
- Valid platform credentials and Gemini API key
- Chromium runtime for Playwright (installed by scripts below)

## Quick Start

1. Clone this repo and open a terminal in project root.
2. Install CLI for your OS.
3. Create `.env` from `.env.example`.
4. Run `cronbot`.

## Install (Cross-OS)

### Windows PowerShell (recommended)

```powershell
powershell -ExecutionPolicy Bypass -File .\install-cli.ps1
```

Optional (local virtual environment instead of user install):

```powershell
powershell -ExecutionPolicy Bypass -File .\install-cli.ps1 -Mode Venv
```

### Windows CMD

```cmd
install-cli.cmd
```

### macOS / Linux

```bash
bash ./install-cli.sh
```

### What the installer does

1. Installs package in editable mode (`pip install -e .`)
2. Installs Playwright Chromium runtime
3. Adds Python scripts directory to your PATH/profile (unless disabled)

After installation, open a new terminal and verify:

```bash
cronbot --help
cronjob --help
```

`cronjob` is an alias of `cronbot`.

## Configuration

Create `.env` file from template:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Set required credentials:

```env
CLG_EMAIL=your_email@example.com
CLG_PASS=your_password_here
GEMINI_API_KEY=your_gemini_api_key_here
```

Do not commit `.env` to source control.

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `CLG_EMAIL` | Yes | - | Login email for diary platform |
| `CLG_PASS` | Yes | - | Login password for diary platform |
| `GEMINI_API_KEY` | Yes | - | API key used for diary text generation |
| `COMPULSORY_SKILLS` | No | `Git, Docker` | Comma-separated skills always included in final payload |
| `WORK_SUMMARY_MIN_CHARS` | No | `300` | Minimum chars for `work_summary` |
| `WORK_SUMMARY_MAX_CHARS` | No | `500` | Maximum chars for `work_summary` |
| `LEARNINGS_MIN_CHARS` | No | `250` | Minimum chars for `learnings` |
| `LEARNINGS_MAX_CHARS` | No | `500` | Maximum chars for `learnings` |
| `BLOCKERS_MIN_CHARS` | No | `100` | Minimum chars for `blockers` |
| `BLOCKERS_MAX_CHARS` | No | `200` | Maximum chars for `blockers` |
| `FIELD_CHAR_TOLERANCE` | No | `40` | Soft deviation allowed around min/max before strict failure |
| `LLM_RATE_LIMIT_RETRY_BASE_SECONDS` | No | `8` | Base backoff seconds for retryable Gemini rate-limit errors |
| `LLM_RATE_LIMIT_RETRY_MAX_WAIT_SECONDS` | No | `300` | Maximum wait seconds per retry |
| `LLM_RATE_LIMIT_MAX_RETRIES` | No | `0` | Retry attempts for rate limits (`0` means unlimited retries) |
| `BROWSER_DEFAULT_TIMEOUT_MS` | No | `45000` | Default UI wait timeout for selectors/actions |
| `BROWSER_NAV_TIMEOUT_MS` | No | `120000` | Navigation/page-load timeout |

Validation rules:

- `*_MIN_CHARS` and `*_MAX_CHARS` must be positive integers
- `FIELD_CHAR_TOLERANCE` must be a non-negative integer
- Each `MIN` must be `<= MAX`
- `LLM_RATE_LIMIT_RETRY_MAX_WAIT_SECONDS` must be `>= LLM_RATE_LIMIT_RETRY_BASE_SECONDS`
- `BROWSER_NAV_TIMEOUT_MS` must be `>= BROWSER_DEFAULT_TIMEOUT_MS`

## Usage

Run the CLI:

```bash
cronbot
```

Single-run force mode (no JSON preview/editor, auto-save after browser fill):

```bash
cronbot -f
cronbot --force
cronbot -force
cronjob -f
cronjob -force
```

Theme options:

```bash
cronbot --theme claude
cronbot --theme clean
```

Bulk mode:

```bash
cronbot --bulk
cronbot --bulk --force
cronbot --bulk -f
cronjob --bulk --force
```

Compatibility alias:

```bash
cronbot --bulk -force
```

This is normalized internally to `--force`.

### Bulk CSV Format

By default, bulk mode reads `bulk.csv` in project root.

Required headers:

```csv
date,description
23-02-2026,Implemented CLI theming and improved date validation flow.
24-02-2026,Handled month/year dropdown logic in datepicker for stable automation.
```

- `date` must be `DD-MM-YYYY`
- `description` must be a non-empty one-line summary
- Invalid rows are logged and skipped (not silently ignored)

You can start from:

```text
bulk.csv.example
```

Create working file:

```bash
cp bulk.csv.example bulk.csv
```

Windows PowerShell:

```powershell
Copy-Item bulk.csv.example bulk.csv
```

### Bulk Flags

- `--bulk`: enable CSV-driven batch run
- `--force` / `-f`: in bulk mode, skip JSON editor and save-confirmation pause, auto-click Save for each row
- `--resume`: skip rows already marked `success` in results CSV
- `--csv-file <path>`: override default `bulk.csv`
- `--results-file <path>`: override default `bulk_results.csv`
- `--artifacts-dir <path>`: override default `bulk_artifacts`
- `--screenshot-on-failure` / `--no-screenshot-on-failure`: browser failure screenshot behavior

## Runtime Flow

1. Choose date (`today` or custom `DD-MM-YYYY`)
2. Enter a one-line task summary
3. Review generated draft preview
4. Edit JSON in local editor
5. Browser opens and fills internship diary
6. Final save confirmation from browser or CLI

`cronbot -f` / `cronbot -force`:

1. Choose date (`today` or custom `DD-MM-YYYY`)
2. Enter a one-line task summary
3. Generate LLM payload
4. Skip JSON preview/editor
5. Fill browser form
6. Auto-click Save and finish

## Bulk Runtime Flow

`cronbot --bulk`:

1. Read CSV rows (`date`, `description`)
2. Generate LLM JSON for each valid row
3. Open editor review for each row
4. Fill browser form for that row
5. Wait for manual Save/CLI confirmation
6. Continue to next row

`cronbot --bulk --force`:

1. Read CSV rows (`date`, `description`)
2. Generate LLM JSON for each valid row
3. Skip editor review
4. Fill browser form
5. Auto-click Save
6. Continue automatically

Outputs:

- `bulk_results.csv`: row-by-row machine-readable status history
- `bulk_artifacts/bulk_run_<RUN_ID>.log`: detailed run log
- `bulk_artifacts/screenshots/<RUN_ID>/...png`: optional browser failure screenshots

## Scheduling Note

Single mode is interactive.
Bulk mode can be interactive or unattended (with `--bulk --force`).

- Use `cronbot` or `cronbot --bulk` when manual validation is required
- Use `cronbot --bulk --force` for unattended scheduler jobs
- `cronbot -f` is semi-automatic (still asks date and task in CLI)

Example cron entry (Linux/macOS):

```cron
0 21 * * 1-5 /usr/bin/env bash -lc 'cronbot --bulk --force --resume'
```

## Troubleshooting

### `cronbot` command not found

- Restart terminal after install (PATH refresh)
- Check script path for your Python user install is in PATH
- Re-run installer with default options

On Windows, user installs typically place scripts under:

```text
C:\Users\<YourUser>\AppData\Roaming\Python\Python3XX\Scripts
```

### Playwright browser launch issues (Linux)

Install OS dependencies:

```bash
python3 -m playwright install-deps chromium
```

### Browser timeouts on weak networks

- Increase browser wait settings in `.env`:
  - `BROWSER_DEFAULT_TIMEOUT_MS=60000`
  - `BROWSER_NAV_TIMEOUT_MS=180000`
- Defaults are already tuned for slower networks:
  - `BROWSER_DEFAULT_TIMEOUT_MS=45000`
  - `BROWSER_NAV_TIMEOUT_MS=120000`

### Config errors for char limits

- Ensure numeric values in `.env`
- Ensure `MIN <= MAX`
- Use a larger `FIELD_CHAR_TOLERANCE` if you want to accept slight variation

### Bulk CSV errors

- Ensure CSV has headers: `date,description`
- Ensure `date` values use `DD-MM-YYYY`
- Ensure `description` is not empty
- Check `bulk_results.csv` and `bulk_artifacts/bulk_run_<RUN_ID>.log` for row-level details

### Gemini rate limiting during bulk

- CLI automatically retries on retryable rate-limit/quota bursts
- For long runs, set:
  - `LLM_RATE_LIMIT_MAX_RETRIES=0` for unlimited retries
  - `LLM_RATE_LIMIT_RETRY_BASE_SECONDS`
  - `LLM_RATE_LIMIT_RETRY_MAX_WAIT_SECONDS`

### Date selected but form not accepted

The selected date can still be rejected by site-side rules (internship/date availability). Try:

- Another valid date in allowed internship range
- Re-running without interacting with datepicker manually during automation

### Editor step failed

- On Windows, default editor fallback is Notepad
- On macOS/Linux, set `EDITOR` if needed, for example:

```bash
export EDITOR=nano
```

## Uninstall

If installed as user package:

```bash
python -m pip uninstall cronbot-cli
```

If installed with Windows venv mode, remove local `.venv` directory from project root.

## Developer Notes

Run directly from source:

```bash
python src/main.py --help
python src/main.py
```

Entry points from package install:

- `cronbot`
- `cronjob`

## Project Layout

| Path | Purpose |
|---|---|
| `src/main.py` | CLI entry and orchestration |
| `src/cronbot/cli/ui.py` | Rich terminal UI panels/prompts |
| `src/cronbot/core/bulk.py` | Bulk CSV parsing, resume signatures, results/log persistence |
| `src/cronbot/core/llm.py` | Gemini draft generation and char-length policy |
| `src/cronbot/core/editor.py` | Local JSON human-review step |
| `src/cronbot/automation/browser.py` | Playwright browser automation |
| `src/cronbot/exceptions.py` | User-facing structured error mapping |
| `install-cli.ps1` / `install-cli.sh` | Cross-OS installer scripts |
| `bulk.csv.example` | Starter template for `--bulk` CSV input |
