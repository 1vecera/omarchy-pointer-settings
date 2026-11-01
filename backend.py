"""Edit literal Omarchy input settings without executing or replacing the user's Lua."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class SettingsError(Exception):
    """A configuration could not be read or safely applied."""


class NeedsDefaults(SettingsError):
    """The user inherits settings that must be read from the running compositor."""


@dataclass(frozen=True)
class Values:
    mouse: float
    mouse_scroll: float
    touchpad: float
    touchpad_scroll: float
    touchpad_adaptive: bool = False
    mouse_adaptive: bool = False


@dataclass(frozen=True)
class Defaults:
    values: Values
    profile: str
    touchpad_name: str | None


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int


TOKEN = re.compile(
    r"--\[(?P<comment_eq>=*)\[.*?\](?P=comment_eq)\]|--[^\n]*"
    r'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    r"|\[(?P<string_eq>=*)\[.*?\](?P=string_eq)\]"
    r"|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
    r"|[A-Za-z_][A-Za-z_0-9]*|\S",
    re.DOTALL,
)


@dataclass(frozen=True)
class Field:
    tokens: tuple[Token, ...]

    def number(self) -> float:
        """Require a finite numeric literal, never an arbitrary Lua expression."""
        try:
            value = float(self.tokens[0].text) if len(self.tokens) == 1 else math.nan
        except ValueError as error:
            raise SettingsError("A speed setting uses an expression instead of a number.") from error
        if not math.isfinite(value):
            raise SettingsError("A speed setting must be a finite numeric literal.")
        return value

    def string(self) -> str:
        """Accept simple quoted strings used by device names and acceleration profiles."""
        text = self.tokens[0].text
        if len(self.tokens) != 1 or text[:1] not in ("'", '"') or "\\" in text:
            raise SettingsError("A device name or profile must be a simple quoted string.")
        return text[1:-1]

    def table(self) -> dict[str, Field]:
        """Find direct table fields while skipping nested tables, strings and comments."""
        tokens = self.tokens
        if tokens[0].text != "{" or tokens[-1].text != "}":
            raise SettingsError("Expected a literal Lua table in input.lua.")
        fields: dict[str, Field] = {}
        index = 1
        while index < len(tokens) - 1:
            if tokens[index].text in (",", ";"):
                index += 1
                continue
            key = tokens[index].text
            if not re.fullmatch(r"[A-Za-z_]\w*", key) or tokens[index + 1].text != "=":
                raise SettingsError("This input table uses unsupported Lua syntax; no settings were changed.")
            start = index + 2
            index = start
            depth = 0
            while index < len(tokens) - 1:
                text = tokens[index].text
                if depth == 0 and text in (",", ";"):
                    break
                if text in ("{", "(", "["):
                    depth += 1
                elif text in ("}", ")", "]"):
                    depth -= 1
                index += 1
            if key in fields or index == start:
                raise SettingsError(f"Ambiguous input setting: {key}.")
            fields[key] = Field(tokens[start:index])
        return fields


def call_tables(source: str, name: str) -> list[dict[str, Field]]:
    """Locate hl.config/hl.device tables without evaluating Lua or matching commented code."""
    tokens = tuple(Token(m[0], m.start(), m.end()) for m in TOKEN.finditer(source) if not m[0].startswith("--"))
    tables: list[dict[str, Field]] = []
    for index in range(len(tokens) - 4):
        if [token.text for token in tokens[index : index + 5]] != ["hl", ".", name, "(", "{"]:
            continue
        start = index + 4
        depth = 0
        for end in range(start, len(tokens)):
            if tokens[end].text == "{":
                depth += 1
            elif tokens[end].text == "}":
                depth -= 1
            if depth == 0:
                tables.append(Field(tokens[start : end + 1]).table())
                break
        else:
            raise SettingsError("An input table is missing its closing brace.")
    return tables


class Document:
    """Read the four supported controls and retain exact spans for minimal edits."""

    def __init__(self, source: str, defaults: Defaults | None = None) -> None:
        self.source = source
        self.defaults = defaults
        try:
            inputs = [table["input"].table() for table in call_tables(source, "config") if "input" in table]
            controls: dict[str, Field] = {}
            pad_controls: dict[str, Field] = {}
            for table in inputs:
                controls.update(table)
                if "touchpad" in table:
                    pad_controls.update(table["touchpad"].table())
            devices: dict[str, dict[str, Field]] = {}
            for table in call_tables(source, "device"):
                name = table["name"].string()
                devices.setdefault(name, {}).update(table)
            touchpad_devices = {
                name: fields for name, fields in devices.items() if re.search(r"touchpad|trackpad", name, re.IGNORECASE)
            }
            mouse_devices = {
                name: fields
                for name, fields in devices.items()
                if name not in touchpad_devices and re.search(r"mouse|pointer", name, re.IGNORECASE)
            }
            if len(touchpad_devices) > 1:
                raise SettingsError("Multiple configured touchpads are not supported yet.")
            if len(mouse_devices) > 1:
                raise SettingsError("Multiple configured mice are not supported yet.")
            touchpad: dict[str, Field] = next(iter(touchpad_devices.values())) if touchpad_devices else {}
            mouse_device: dict[str, Field] = next(iter(mouse_devices.values())) if mouse_devices else {}
            if defaults is None and (
                not {"sensitivity", "scroll_factor", "accel_profile"} <= controls.keys()
                or "scroll_factor" not in pad_controls
                or not {"sensitivity", "accel_profile"} <= touchpad.keys()
            ):
                raise NeedsDefaults("Read inherited input settings from Hyprland.")
            inherited = defaults or Defaults(Values(0, 1, 0, 0.4, False), "", None)
            self.touchpad_name = next(iter(touchpad_devices), inherited.touchpad_name)
            self.mouse_name = next(iter(mouse_devices), None)
            global_mouse_profile = (
                controls["accel_profile"].string() if "accel_profile" in controls else inherited.profile
            )
            mouse_profile_field = mouse_device.get("accel_profile")
            self.mouse_profile = mouse_profile_field.string() if mouse_profile_field else global_mouse_profile
            self.profile = touchpad["accel_profile"].string() if "accel_profile" in touchpad else self.mouse_profile
            if self.mouse_profile not in ("flat", "adaptive", ""):
                raise SettingsError("The mouse has a custom profile; the normal mouse slider would have no effect.")
            self.custom = self.profile.startswith("custom ")
            self.step = 1.0
            if self.custom:
                parts = self.profile.split()
                if len(parts) != 4 or float(parts[2]) != 0:
                    raise SettingsError("This app supports a linear touchpad motion curve with two points.")
                self.step = float(parts[1])
                endpoint = float(parts[3])
                if not math.isfinite(self.step) or self.step <= 0 or not math.isfinite(endpoint) or endpoint <= 0:
                    raise SettingsError("The touchpad motion curve is not valid.")
                touchpad_speed = endpoint / self.step
                motion_field = touchpad["accel_profile"]
            else:
                if self.profile not in ("flat", "adaptive", ""):
                    raise SettingsError("The touchpad acceleration profile is not supported.")
                motion_field = touchpad.get("sensitivity")
                touchpad_speed = motion_field.number() if motion_field else inherited.values.touchpad
            self.fields: dict[str, Field | None] = {
                "mouse": controls.get("sensitivity"),
                "mouse_scroll": controls.get("scroll_factor"),
                "touchpad": motion_field,
                "touchpad_scroll": pad_controls.get("scroll_factor"),
                "touchpad_adaptive": touchpad.get("accel_profile"),
                "mouse_adaptive": mouse_device.get("accel_profile") or controls.get("accel_profile"),
            }
            resolved = {
                key: field.number() if field is not None else getattr(inherited.values, key)
                for key, field in self.fields.items()
                if key not in ("touchpad", "touchpad_adaptive", "mouse_adaptive")
            }
            self.values = Values(
                mouse=resolved["mouse"],
                mouse_scroll=resolved["mouse_scroll"],
                touchpad=touchpad_speed,
                touchpad_scroll=resolved["touchpad_scroll"],
                touchpad_adaptive=self.profile == "adaptive",
                mouse_adaptive=self.mouse_profile == "adaptive",
            )
        except (KeyError, ValueError, IndexError) as error:
            raise SettingsError(f"Cannot read the expected literal settings in input.lua: {error}") from error

    def render(self, values: Values) -> str:
        """Replace only changed values; leave scrolling curves, gestures and keyboard settings intact."""
        limits = {
            "mouse": (-1.0, 1.0),
            "mouse_scroll": (0.1, 2.0),
            "touchpad": (0.05, 2.0) if self.custom else (-1.0, 1.0),
            "touchpad_scroll": (0.1, 2.0),
        }
        edits: list[tuple[int, int, str]] = []
        missing: dict[str, float | str] = {}
        for key, (minimum, maximum) in limits.items():
            value: float = getattr(values, key)
            if value == getattr(self.values, key):
                continue
            if not math.isfinite(value) or not minimum <= value <= maximum:
                raise SettingsError(
                    f"{key.replace('_', ' ').capitalize()} must be between {minimum:g} and {maximum:g}."
                )
            if key.startswith("touchpad") and self.touchpad_name is None:
                raise SettingsError("No touchpad was detected or configured.")
            replacement = f"{value:.10g}"
            if key == "touchpad" and self.custom:
                replacement = f'"custom {self.step:.10g} 0 {value * self.step:.10g}"'
            field = self.fields[key]
            if field is None:
                missing[key] = value
            else:
                edits.append((field.tokens[0].start, field.tokens[-1].end, replacement))
        adaptive = values.touchpad_adaptive
        if adaptive != self.values.touchpad_adaptive:
            if self.custom:
                raise SettingsError("Adaptive acceleration cannot be toggled for a custom touchpad profile.")
            if self.touchpad_name is None:
                raise SettingsError("No touchpad was detected or configured.")
            profile_field = self.fields["touchpad_adaptive"]
            if profile_field is None:
                missing["touchpad_adaptive"] = "adaptive" if adaptive else "flat"
            else:
                edits.append(
                    (
                        profile_field.tokens[0].start,
                        profile_field.tokens[-1].end,
                        f'"{"adaptive" if adaptive else "flat"}"',
                    )
                )
        mouse_adaptive = values.mouse_adaptive
        if mouse_adaptive != self.values.mouse_adaptive:
            if self.mouse_profile not in ("flat", "adaptive", ""):
                raise SettingsError("Adaptive acceleration cannot be toggled for a custom mouse profile.")
            profile_field = self.fields["mouse_adaptive"]
            if profile_field is None:
                missing["mouse_adaptive"] = "adaptive" if mouse_adaptive else "flat"
            else:
                edits.append(
                    (
                        profile_field.tokens[0].start,
                        profile_field.tokens[-1].end,
                        f'"{"adaptive" if mouse_adaptive else "flat"}"',
                    )
                )
        result = self.source
        for start, end, replacement in sorted(edits, reverse=True):
            result = result[:start] + replacement + result[end:]
        if not edits and not missing:
            return result
        # Pin an inherited touchpad speed before changing the global mouse value.
        if self.touchpad_name is not None and self.fields["touchpad"] is None:
            missing["touchpad"] = values.touchpad
        additions: list[str] = []
        input_lines: list[str] = []
        for key, option in (("mouse", "sensitivity"), ("mouse_scroll", "scroll_factor")):
            if key in missing:
                input_lines.append(f"    {option} = {missing[key]:.10g},")
        if "touchpad_scroll" in missing:
            input_lines.append(f"    touchpad = {{ scroll_factor = {missing['touchpad_scroll']:.10g} }},")
        if "mouse_adaptive" in missing and not self.mouse_name:
            input_lines.append(f'    accel_profile = "{missing["mouse_adaptive"]}",')
        if input_lines:
            additions.append("hl.config({\n  input = {\n" + "\n".join(input_lines) + "\n  },\n})")
        if "touchpad" in missing:
            name = self.touchpad_name
            if name is None or not re.fullmatch(r"[\w .:/-]+", name):
                raise SettingsError("This touchpad name cannot be safely added to the Lua configuration.")
            device_fields = [f'name = "{name}"']
            if "touchpad" in missing:
                device_fields.append(f"sensitivity = {missing['touchpad']:.10g}")
            if "touchpad_adaptive" in missing:
                device_fields.append(f'accel_profile = "{missing["touchpad_adaptive"]}"')
            additions.append("hl.device({ " + ", ".join(device_fields) + " })")
        if "mouse_adaptive" in missing:
            profile = missing["mouse_adaptive"]
            if self.mouse_name:
                additions.append(f'hl.device({{ name = "{self.mouse_name}", accel_profile = "{profile}" }})')
        if additions:
            result = result.rstrip() + "\n\n-- Pointer Settings overrides.\n" + "\n".join(additions) + "\n"
        return result


def run_hyprctl(arguments: list[str]) -> str:
    """Bound compositor calls and turn connection/process failures into actionable UI errors."""
    try:
        command = os.environ.get("POINTER_SETTINGS_HYPRCTL", "hyprctl")
        result = subprocess.run([command, *arguments], capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise SettingsError("Cannot reach Hyprland. Run this app inside your Hyprland session.") from error
    return result.stdout.strip()


def atomic_write(path: Path, text: str, mode: int) -> None:
    """Replace a complete file on the same filesystem, retaining its permissions."""
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Controller:
    """Back up and validate each save, reject stale edits and restore failed changes."""

    def __init__(self, config: Path, state: Path, runner: Callable[[list[str]], str] = run_hyprctl) -> None:
        self.config = config.resolve()
        self.state = state
        self.run = runner
        self.previous: str | None = None
        self.saved: str | None = None
        self.backup: Path | None = None

    def load(self) -> Document:
        """Read a fresh snapshot so another editor's work can never be silently overwritten."""
        try:
            source = self.config.read_text()
            try:
                return Document(source)
            except NeedsDefaults:
                return Document(source, self._defaults())
        except OSError as error:
            raise SettingsError(f"Cannot read {self.config}: {error.strerror}") from error

    def _defaults(self) -> Defaults:
        """Resolve inherited values and a single touchpad without changing the compositor."""
        try:
            mouse = float(json.loads(self.run(["-j", "getoption", "input:sensitivity"]))["float"])
            wheel = float(json.loads(self.run(["-j", "getoption", "input:scroll_factor"]))["float"])
            scroll = float(json.loads(self.run(["-j", "getoption", "input:touchpad:scroll_factor"]))["float"])
            profile = str(json.loads(self.run(["-j", "getoption", "input:accel_profile"]))["str"])
            if profile == "[[EMPTY]]":
                profile = ""
            pointers = json.loads(self.run(["-j", "devices"]))["mice"]
            names: list[str] = [item["name"] for item in pointers if re.search("touchpad|trackpad", item["name"], re.I)]
            if len(names) > 1:
                raise SettingsError("Multiple connected touchpads are not supported yet.")
            if not all(math.isfinite(value) for value in (mouse, wheel, scroll)):
                raise SettingsError("Hyprland returned an invalid speed setting.")
            return Defaults(
                Values(mouse, wheel, mouse, scroll, profile == "adaptive", profile == "adaptive"),
                profile,
                names[0] if names else None,
            )
        except (ValueError, KeyError, TypeError) as error:
            raise SettingsError("Cannot read the active Hyprland input defaults.") from error

    def apply(self, document: Document, values: Values) -> Document:
        """Save the panel's latest values; opening the panel alone never changes input behavior."""
        updated = document.render(values)
        if updated == document.source:
            return document
        self._save(document.source, updated)
        self.previous, self.saved = document.source, updated
        return Document(updated, document.defaults)

    def undo(self) -> Document:
        """Restore the last successful save only when the file has not changed since."""
        if self.previous is None or self.saved is None:
            raise SettingsError("There is no change to undo in this window.")
        previous = self.previous
        self._save(self.saved, previous)
        self.previous = self.saved = None
        return self.load()

    def _reload(self) -> None:
        response = self.run(["reload", "config-only"])
        if response.strip() != "ok":
            raise SettingsError(f"Hyprland rejected the reload: {response}")
        errors = self.run(["configerrors"]).strip()
        if errors:
            raise SettingsError(f"Hyprland reported a configuration error: {errors}")

    def _save(self, before: str, after: str) -> None:
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.state / "save.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.config.read_text() != before:
                raise SettingsError("Settings changed in another editor. Click Reload and try again.")
            existing_errors = self.run(["configerrors"]).strip()
            if existing_errors:
                raise SettingsError(f"Fix the existing Hyprland configuration errors first: {existing_errors}")
            backups = self.state / "backups"
            backups.mkdir(exist_ok=True, mode=0o700)
            backup = backups / f"input-{datetime.now():%Y%m%d-%H%M%S-%f}.lua"
            with backup.open("x") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(before)
            self.backup = backup
            mode = stat.S_IMODE(self.config.stat().st_mode)
            if self.config.read_text() != before:
                raise SettingsError("Settings changed while preparing the save. Click Reload and try again.")
            atomic_write(self.config, after, mode)
            try:
                self._reload()
            except SettingsError as error:
                if self.config.read_text() != after:
                    raise SettingsError(f"{error}\nThe file changed again; recover from {backup} if needed.") from error
                atomic_write(self.config, before, mode)
                try:
                    self._reload()
                except SettingsError as rollback_error:
                    raise SettingsError(
                        f"The original file was restored, but reload failed: {rollback_error}"
                    ) from error
                raise SettingsError(f"The change was rolled back. {error}") from error
