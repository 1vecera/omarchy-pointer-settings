# Contributing

Keep the plugin small, local, and native to Omarchy. A useful issue includes your Omarchy and Hyprland versions, acceleration profile, expected behavior, and the exact error. Use a minimal synthetic configuration when reporting a parser problem; full desktop configs can contain personal details.

## Local checks

Python checks need `uv` and Python 3.13 or newer. No runtime Python dependencies are required.

```sh
uv run --no-project --no-config --python 3.13 python -B -m unittest discover -s tests -v
uvx ruff@0.16.5 check .
uvx ruff@0.16.5 format --check .
uvx pyright@1.1.413
git diff --check
```

Tests use disposable configurations under `tmp/` and a fake compositor. They cover stock and partial configs, independent touchpad settings, minimal edits, custom curves, outside changes, backups, rollback, and undo across helper processes. CI runs these Python checks; it does not run a desktop session.

## Isolated UI test

On Omarchy, with `xorg-server-xvfb`, `xorg-xauth`, D-Bus, AT-SPI, Quickshell, `ripgrep`, and `uv` installed:

```sh
bash tests/run_offscreen.sh
```

The runner creates a virtual X11 display, private session and accessibility buses, isolated XDG directories, and a fake `hyprctl`. It exercises the production QML and Python helper without changing the live desktop or input configuration. Screenshots and logs remain under `tmp/ui.*`. The test checks debounce, edits during a save, undo, rejected-save rollback, and recovery. It does not prove physical pointer feel or the live Wayland popup.

`tests/run_ui_smoke.sh` can also run in another isolated harness that provides `OFFSCREEN_ARTIFACT_DIR`, `OFFSCREEN_SESSION_ROOT`, private buses, and XDG paths below that session root. Do not point it at your live desktop.

## Source layout

| File | Responsibility |
| --- | --- |
| `Widget.qml` | Bar icon and Omarchy keyboard-aware popup. |
| `SettingsView.qml` | Slider state, debounce, queued saves, and helper process. |
| `SliderRow.qml` | Native slider, value display, and keyboard controls. |
| `settings.py` | JSON interface, revision tokens, and persistent guarded undo. |
| `backend.py` | Literal Lua editing, inherited defaults, atomic saves, backups, and rollback. |
| `manifest.json` | Omarchy plugin identity and entry point. |

Helpers run with Python's `-B` flag so Python does not create bytecode files inside the installed plugin and trigger Omarchy's file watcher.

For a local working copy, `bash install.sh` validates and copies the runtime files, backs up the previous plugin and bar layout, and enables the icon. This copy is not managed by `omarchy plugin update`; rerun the script after edits. Do not run the installer against your live desktop as part of automated tests.

Validate a clean checkout or staged package with `omarchy plugin validate /path/to/plugin`. The validator rejects symlinks, including temporary QML import links under the ignored `tmp/` directory after UI tests.

## Pull requests

Describe the user-visible problem, the resulting behavior, and the checks you ran. Keep parser changes covered by small synthetic fixtures and retain the refusal to overwrite outside edits. UI changes should include an offscreen screenshot. Do not add runtime downloads, background services, or generated files.
