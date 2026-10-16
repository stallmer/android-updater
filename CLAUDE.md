# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`android-updater` is a stdlib-only (no dependencies) Python 3.11+ CLI that updates a watchlist of Android apps on a USB-connected phone via `adb`. See `README.md` for user-facing usage, file locations, and limitations.

## Commands

```
python -m venv .venv && .venv/bin/pip install -e .   # install (hatchling build, src/ layout)
.venv/bin/android-updater <add|add-direct|remove|list|check|update|digest|install-timer>
.venv/bin/android-updater check                       # no phone needed
.venv/bin/android-updater update --dry-run            # needs a phone
.venv/bin/android-updater digest --print              # print instead of notify-send
```

There is no test suite, linter, or formatter configured.

## Architecture

Entry point is `cli.py:main` (argparse subcommands, one `cmd_*` function each). The flow shared by `check`, `update`, and `digest`:

1. **`watchlist.py`** loads `Config` from `~/.config/android-updater/config.toml`: `packages` (F-Droid IDs) plus `[[app]]` direct sources.
2. **`repo.py`** fetches/caches the F-Droid index (hash-checked against `entry.json`) and `best_release()` picks the newest stable release compatible with the device's SDK and ABIs; `download()` verifies SHA-256.
3. **`direct.py`** resolves a direct source into the same `repo.Release` type (version-code text URL + `{abi}` APK URL template, no hash check).
4. **`updater.py`** merges both into `latest_releases()`, `find_updates()` keeps only installed apps with a strictly higher `versionCode` (upgrade-only), and `apply()` downloads and installs each, collecting per-package errors so one failure doesn't abort the rest.
5. **`adb.py`** wraps the `adb` binary (single-device enforcement, SDK/ABI info, installed versions, install).
6. **`digest.py` + `state.py`**: `update` (including `--dry-run`) records phone-installed versions in `state.json`; `digest` compares latest releases against that state, so it works with the phone unplugged, and only notifies when something is newer than what was last reported. `install-timer` (in `cli.py`) writes systemd user units pointing at the absolute path of the installed script.

`paths.py` centralizes XDG config/cache/state directories (honoring `XDG_*_HOME`).

`repo.Release` is the common currency between F-Droid and direct sources; new source types should produce it.
