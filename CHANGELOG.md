# Changelog

## 0.4.0 — 2026-10-31

- Add independent adaptive-acceleration toggles for mouse and touchpad.
- Preserve explicit per-device acceleration profiles when applying changes.
- Keep compatibility with Hyprland's unset global acceleration profile.

## 0.3.0 — 2026-09-24

First public release.

- Native Omarchy bar popup with separate mouse and touchpad motion and scroll controls.
- Automatic saving after a 300 ms pause, including edits made while an earlier save is running.
- Backups, persistent undo, concurrent-edit checks, and rollback on rejected configuration reloads.
- Support for stock, partial, and explicit Lua input configurations, plus desktops without a touchpad.
- Independent touchpad sensitivity and linear custom motion curves with preserved scrolling points.
- Keyboard controls, a standalone offscreen UI test, and automated Python checks.
