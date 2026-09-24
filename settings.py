"""Small JSON bridge between the Omarchy panel and the configuration editor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend import Controller, SettingsError, Values, atomic_write


def main() -> int:
    """Use snapshot tokens for saves and retain one guarded undo across panel openings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "apply", "undo"))
    parser.add_argument("payload", nargs="?", default="{}")
    args = parser.parse_args()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    state_home = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    controller = Controller(config_home / "hypr/input.lua", state_home / "omarchy/pointer-settings")
    history = controller.state / "undo.json"
    try:
        document = controller.load()
        if history.exists():
            saved = json.loads(history.read_text())
            if saved["config"] == str(controller.config):
                controller.previous, controller.saved = saved["before"], saved["after"]
        if args.action == "apply":
            request = json.loads(args.payload)
            if request["revision"] != hashlib.sha256(document.source.encode()).hexdigest():
                raise SettingsError("Settings changed in another editor. Click Reload before applying.")
            document = controller.apply(document, Values(**request["values"]))
            if controller.previous is not None:
                atomic_write(
                    history,
                    json.dumps(
                        {"config": str(controller.config), "before": controller.previous, "after": controller.saved}
                    ),
                    0o600,
                )
        elif args.action == "undo":
            document = controller.undo()
            history.unlink(missing_ok=True)
        state: dict[str, Any] = {
            "revision": hashlib.sha256(document.source.encode()).hexdigest(),
            "values": asdict(document.values),
            "custom": document.custom,
            "touchpadName": document.touchpad_name,
            "hasTouchpad": document.touchpad_name is not None,
            "canUndo": controller.previous is not None and controller.saved == document.source,
        }
        print(json.dumps({"ok": True, "state": state}))
        return 0
    except (SettingsError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
