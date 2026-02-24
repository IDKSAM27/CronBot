# Changelog

All notable changes to this project should be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added

- Single-run force mode: `cronbot -f` / `cronbot --force` / `cronbot -force`.
- Bulk mode with CSV input, resume support, row-level results, and detailed run artifacts.
- Gemini rate-limit retry policy with configurable backoff settings.
- Browser failure screenshot capture during bulk runs.

### Changed

- CLI now supports both interactive and force workflows for single and bulk runs.
- README expanded with force/bulk usage, CSV format, retry configuration, and troubleshooting.

## [1.0.0]

### Added

- Initial tagged release.
- Interactive internship diary automation flow:
  - LLM generation
  - JSON review/edit
  - Browser fill and save confirmation

## Changelog Workflow

Use this workflow for each release:

1. Add every user-visible change under `## [Unreleased]` while developing.
2. Keep entries grouped under: `Added`, `Changed`, `Fixed`, `Removed`, `Security`.
3. When cutting a release, rename `Unreleased` to the version heading (for example `## [1.1.0] - 2026-02-24`) and start a fresh `Unreleased` section.
4. Keep entries user-focused: behavior changes, compatibility, migration notes.
5. Link each release to PR/commit references if your repo workflow includes them.
