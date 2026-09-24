"""Exercise edits and recovery against disposable configs, never the real compositor."""

import json
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from backend import Controller, Defaults, Document, NeedsDefaults, SettingsError, Values

SOURCE = (Path(__file__).parent / "fixtures/input.lua").read_text()
DEFAULTS = Defaults(Values(0, 1, 0, 0.4), "adaptive", "example-touchpad")
STOCK = "-- User overrides\n-- hl.config({ input = { sensitivity = 0.8 } })\n"


def active_defaults(args):
    """Model inherited Omarchy settings, with no real compositor connection."""
    if args == ["-j", "devices"]:
        return json.dumps({"mice": [{"name": "example-mouse"}, {"name": "example-touchpad"}]})
    if args[:2] == ["-j", "getoption"]:
        options = {
            "input:sensitivity": {"float": 0},
            "input:scroll_factor": {"float": 1},
            "input:touchpad:scroll_factor": {"float": 0.4},
            "input:accel_profile": {"str": "adaptive"},
        }
        return json.dumps(options[args[2]])
    return "ok" if args == ["reload", "config-only"] else ""


class DocumentTests(unittest.TestCase):
    def test_stock_config_needs_runtime_defaults_and_opening_preserves_it(self):
        with self.assertRaises(NeedsDefaults):
            Document(STOCK)
        document = Document(STOCK, DEFAULTS)
        self.assertEqual(document.values, DEFAULTS.values)
        self.assertEqual(document.render(document.values), STOCK)

    def test_stock_mouse_change_pins_touchpad_and_preserves_comments(self):
        document = Document(STOCK, DEFAULTS)
        rendered = document.render(replace(document.values, mouse=-0.25))
        self.assertTrue(rendered.startswith(STOCK))
        self.assertIn('hl.device({ name = "example-touchpad", sensitivity = 0 })', rendered)
        reloaded = Document(rendered, replace(DEFAULTS, values=Values(-0.25, 1, -0.25, 0.4)))
        self.assertEqual(reloaded.values, Values(-0.25, 1, 0, 0.4))
        again = reloaded.render(replace(reloaded.values, mouse=-0.4))
        self.assertEqual(again.count("-- Pointer Settings overrides."), 1)
        self.assertEqual(again.count("hl.device("), 1)

    def test_stock_all_controls_survive_a_reload(self):
        document = Document(STOCK, DEFAULTS)
        chosen = Values(-0.3, 0.8, 0.2, 0.6)
        self.assertEqual(Document(document.render(chosen), DEFAULTS).values, chosen)

    def test_partial_config_inherits_and_only_changes_effective_fields(self):
        source = "hl.config({ input = { sensitivity = 0.1, touchpad = { natural_scroll = true } } })\n"
        source += "hl.config({ input = { sensitivity = 0.2 } })\n"
        source += 'hl.device({ name = "example-touchpad", sensitivity = -0.1 })\n'
        document = Document(source, DEFAULTS)
        self.assertEqual(document.values, Values(0.2, 1, -0.1, 0.4))
        actual = document.render(replace(document.values, mouse=0.3, touchpad_scroll=0.7))
        self.assertIn("sensitivity = 0.1", actual)
        self.assertIn("natural_scroll = true", actual)
        self.assertNotIn("sensitivity = 0.2", actual)
        self.assertEqual(Document(actual, DEFAULTS).values, Values(0.3, 1, -0.1, 0.7))

    def test_multiple_overrides_for_same_touchpad_use_last_value(self):
        source = SOURCE + '\nhl.device({ name = "example-touchpad", accel_profile = "adaptive" })\n'
        document = Document(source)
        rendered = document.render(replace(document.values, touchpad=-0.2))
        self.assertFalse(document.custom)
        self.assertEqual(Document(rendered).values.touchpad, -0.2)
        self.assertIn('"custom 1 0 0.3771283355"', rendered)

    def test_mouse_only_desktop_does_not_create_a_touchpad(self):
        document = Document(STOCK, replace(DEFAULTS, touchpad_name=None))
        rendered = document.render(replace(document.values, mouse=-0.2, mouse_scroll=0.8))
        self.assertIsNone(document.touchpad_name)
        self.assertNotIn("hl.device(", rendered)
        with self.assertRaisesRegex(SettingsError, "No touchpad"):
            document.render(replace(document.values, touchpad=0.1))

    def test_untouched_setting_outside_slider_range_is_preserved(self):
        document = Document(SOURCE.replace("scroll_factor = 1.2", "scroll_factor = 3.5"))
        actual = document.render(replace(document.values, mouse=0.1))
        self.assertEqual(Document(actual).values.mouse_scroll, 3.5)

    def test_two_configured_touchpads_are_rejected(self):
        source = SOURCE + '\nhl.device({ name = "second-touchpad", sensitivity = 0.2 })\n'
        with self.assertRaisesRegex(SettingsError, "Multiple configured"):
            Document(source, DEFAULTS)

    def test_unsafe_detected_device_name_is_not_written_as_lua(self):
        document = Document(STOCK, replace(DEFAULTS, touchpad_name='touchpad"; os.execute("bad")'))
        with self.assertRaisesRegex(SettingsError, "safely added"):
            document.render(replace(document.values, mouse=0.1))

    def test_mouse_change_is_one_literal(self):
        document = Document(SOURCE)
        self.assertEqual(document.values.mouse, 0.2)
        self.assertEqual(document.touchpad_name, "example-touchpad")
        actual = document.render(replace(document.values, mouse=-0.25))
        self.assertEqual(actual, SOURCE.replace("sensitivity = 0.2", "sensitivity = -0.25"))

    def test_touchpad_changes_motion_without_changing_scroll_curve(self):
        document = Document(SOURCE)
        actual = document.render(replace(document.values, touchpad=0.5))
        self.assertEqual(actual, SOURCE.replace('"custom 1 0 0.3771283355"', '"custom 1 0 0.5"'))
        self.assertEqual(Document(actual).values.touchpad, 0.5)

    def test_touchpad_gain_accounts_for_curve_step(self):
        document = Document(SOURCE.replace("custom 1 0 0.3771283355", "custom 2 0 0.8"))
        self.assertEqual(document.values.touchpad, 0.4)
        self.assertIn('"custom 2 0 1.2"', document.render(replace(document.values, touchpad=0.6)))

    def test_adaptive_touchpad_uses_its_own_sensitivity(self):
        document = Document(SOURCE.replace("custom 1 0 0.3771283355", "adaptive"))
        actual = document.render(replace(document.values, touchpad=-0.3))
        self.assertEqual(Document(actual).values.mouse, 0.2)
        self.assertEqual(Document(actual).values.touchpad, -0.3)

    def test_noop_preserves_precision_and_all_bytes(self):
        document = Document(SOURCE)
        self.assertEqual(document.render(document.values), SOURCE)

    def test_unsupported_configs_fail_closed(self):
        for source in (
            SOURCE.replace("sensitivity = 0.2", "sensitivity = 0.2 + 0.1"),
            SOURCE.replace("sensitivity = 0.2,", "sensitivity = 0.2, sensitivity = 0.4,"),
            SOURCE.replace("custom 1 0 0.3771283355", "custom 1 0 0.4 0.9"),
            SOURCE.replace('accel_profile = "flat"', 'accel_profile = "custom 1 0 1"'),
        ):
            with self.subTest(source=source), self.assertRaises(SettingsError):
                Document(source)

    def test_nonfinite_and_out_of_bounds_values_are_rejected(self):
        document = Document(SOURCE)
        for value in (float("nan"), float("inf"), -1.1, 1.1):
            with self.subTest(value=value), self.assertRaises(SettingsError):
                document.render(replace(document.values, mouse=value))


class SaveTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "tmp"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.config = self.directory / "input.lua"
        self.config.write_text(SOURCE)
        self.config.chmod(0o640)
        self.calls = []

        def run(args):
            self.calls.append(args)
            return "ok" if args[0] == "reload" else ""

        self.controller = Controller(self.config, self.directory / "state", run)

    def test_stock_first_save_and_undo_restore_exact_original(self):
        self.config.write_text(STOCK)
        self.controller.run = active_defaults
        document = self.controller.load()
        self.assertFalse((self.directory / "state").exists())
        self.assertEqual(document.values, DEFAULTS.values)
        applied = self.controller.apply(document, replace(document.values, mouse=-0.2))
        self.assertEqual(applied.values, Values(-0.2, 1, 0, 0.4))
        self.assertEqual(self.controller.undo().source, STOCK)
        self.assertEqual(self.config.read_text(), STOCK)

    def test_invalid_compositor_defaults_do_not_write_anything(self):
        self.config.write_text(STOCK)
        for response in ("not JSON", '{"float": "nan"}', "{}"):
            self.controller.run = lambda args, value=response: value
            with self.subTest(response=response), self.assertRaises(SettingsError):
                self.controller.load()
        self.assertEqual(self.config.read_text(), STOCK)
        self.assertFalse((self.directory / "state").exists())

    def test_two_connected_touchpads_are_rejected_before_writing(self):
        self.config.write_text(STOCK)
        self.controller.run = lambda args: (
            json.dumps({"mice": [{"name": "one-touchpad"}, {"name": "two-trackpad"}]})
            if args == ["-j", "devices"]
            else active_defaults(args)
        )
        with self.assertRaisesRegex(SettingsError, "Multiple connected"):
            self.controller.load()
        self.assertEqual(self.config.read_text(), STOCK)

    def test_save_and_undo_preserve_permissions_and_keep_backup(self):
        document = self.controller.load()
        applied = self.controller.apply(document, replace(document.values, mouse=0.1, touchpad_scroll=0.8))
        self.assertEqual(applied.values.mouse, 0.1)
        self.assertEqual(applied.values.touchpad_scroll, 0.8)
        self.assertEqual(self.controller.backup.read_text(), SOURCE)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE(self.controller.backup.stat().st_mode), 0o600)
        self.assertIn(["reload", "config-only"], self.calls)
        self.controller.undo()
        self.assertEqual(self.config.read_text(), SOURCE)
        self.assertIsNone(self.controller.previous)

    def test_stale_snapshot_cannot_overwrite_other_edits(self):
        document = self.controller.load()
        self.config.write_text(SOURCE + "-- another editor\n")
        with self.assertRaisesRegex(SettingsError, "another editor"):
            self.controller.apply(document, replace(document.values, mouse=0.1))
        self.assertEqual(self.config.read_text(), SOURCE + "-- another editor\n")
        self.assertEqual(self.calls, [])

    def test_existing_compositor_errors_prevent_write(self):
        self.controller.run = lambda args: "Existing unrelated configuration error"
        document = self.controller.load()
        with self.assertRaisesRegex(SettingsError, "existing Hyprland"):
            self.controller.apply(document, replace(document.values, mouse=0.1))
        self.assertEqual(self.config.read_text(), SOURCE)

    def test_reload_failure_restores_original_and_reloads_it(self):
        checks = iter(["", "bad configuration", ""])
        self.controller.run = lambda args: "ok" if args[0] == "reload" else next(checks)
        document = self.controller.load()
        with self.assertRaisesRegex(SettingsError, "rolled back"):
            self.controller.apply(document, replace(document.values, mouse=0.1))
        self.assertEqual(self.config.read_text(), SOURCE)
        self.assertIsNone(self.controller.previous)

    def test_external_change_during_failure_is_not_clobbered(self):
        def run(args):
            if args[0] == "reload":
                self.config.write_text(SOURCE + "-- external edit\n")
                raise SettingsError("Disconnected")
            return ""

        self.controller.run = run
        document = self.controller.load()
        with self.assertRaisesRegex(SettingsError, "file changed again"):
            self.controller.apply(document, replace(document.values, mouse=0.1))
        self.assertEqual(self.config.read_text(), SOURCE + "-- external edit\n")

    def test_noop_never_touches_compositor(self):
        document = self.controller.load()
        self.controller.apply(document, document.values)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.directory / "state").exists())


if __name__ == "__main__":
    unittest.main()
