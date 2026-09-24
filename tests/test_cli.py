"""Run the real helper across process boundaries using a private config and fake hyprctl."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "tests/fixtures/input.lua").read_text()


class CliTests(unittest.TestCase):
    def test_status_apply_restart_undo_and_stale_edits(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as temporary:
            directory = Path(temporary)
            config = directory / "config/hypr/input.lua"
            config.parent.mkdir(parents=True)
            config.write_text(SOURCE)
            binary = directory / "bin/hyprctl"
            binary.parent.mkdir()
            binary.write_text('#!/bin/sh\nif [ "$1" = reload ]; then echo ok; fi\n')
            binary.chmod(0o755)
            environment = {
                **os.environ,
                "XDG_CONFIG_HOME": str(directory / "config"),
                "XDG_STATE_HOME": str(directory / "state"),
                "PATH": str(binary.parent) + os.pathsep + os.environ["PATH"],
                "HYPRLAND_INSTANCE_SIGNATURE": "isolated-test",
            }

            def call(action, payload=None):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "settings.py"), action, json.dumps(payload or {})],
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(result.stderr, "")
                return result.returncode, json.loads(result.stdout)

            code, initial = call("status")
            self.assertEqual(code, 0)
            self.assertFalse((directory / "state").exists())
            request = initial["state"]
            request["values"]["mouse"] = 0.05
            request["values"]["touchpad"] = 0.45
            code, applied = call("apply", request)
            self.assertEqual(code, 0, applied)
            self.assertTrue(applied["state"]["canUndo"])
            self.assertIn('accel_profile = "custom 1 0 0.45"', config.read_text())
            self.assertNotEqual(call("apply", request)[0], 0)
            self.assertTrue(call("status")[1]["state"]["canUndo"])
            self.assertEqual(call("undo")[0], 0)
            self.assertEqual(config.read_text(), SOURCE)
            self.assertFalse(call("status")[1]["state"]["canUndo"])


if __name__ == "__main__":
    unittest.main()
