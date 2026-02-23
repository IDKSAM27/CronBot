# Cronbot CLI

Cronbot automates internship diary entry with a human-in-the-loop flow:

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

Validation rules:

- `*_MIN_CHARS` and `*_MAX_CHARS` must be positive integers
- `FIELD_CHAR_TOLERANCE` must be a non-negative integer
- Each `MIN` must be `<= MAX`

## Usage

Run the CLI:

```bash
cronbot
```

Theme options:

```bash
cronbot --theme claude
cronbot --theme clean
```

## Runtime Flow

1. Choose date (`today` or custom `DD-MM-YYYY`)
2. Enter a one-line task summary
3. Review generated draft preview
4. Edit JSON in local editor
5. Browser opens and fills internship diary
6. Final save confirmation from browser or CLI

## Scheduling Note

Current flow is interactive (date/task prompt, JSON review, save confirmation), so it is not fully unattended.

- Use scheduler for reminder-style runs when you are present
- For true unattended cron jobs, a future non-interactive mode is needed

Example cron entry (Linux/macOS):

```cron
0 21 * * 1-5 /usr/bin/env bash -lc 'cronbot'
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

### Config errors for char limits

- Ensure numeric values in `.env`
- Ensure `MIN <= MAX`
- Use a larger `FIELD_CHAR_TOLERANCE` if you want to accept slight variation

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
| `src/cronbot/core/llm.py` | Gemini draft generation and char-length policy |
| `src/cronbot/core/editor.py` | Local JSON human-review step |
| `src/cronbot/automation/browser.py` | Playwright browser automation |
| `src/cronbot/exceptions.py` | User-facing structured error mapping |
| `install-cli.ps1` / `install-cli.sh` | Cross-OS installer scripts |
