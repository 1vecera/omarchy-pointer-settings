#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
config_root="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy"
state_root="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/pointer-settings"
plugin_id="daniel.pointer-settings"
destination="$config_root/plugins/$plugin_id"

for executable in uv omarchy omarchy-shell; do
  command -v "$executable" >/dev/null || { echo "Missing dependency: $executable" >&2; exit 1; }
done
uv run --no-project --no-config --python /usr/bin/python python -c 'import sys; assert sys.version_info >= (3, 13)'
mkdir -p "$config_root/plugins" "$state_root/install-backups"
staging="$(mktemp -d "$config_root/.pointer-settings.XXXXXX")"
trap 'rm -rf -- "$staging"' EXIT
for file in Widget.qml SettingsView.qml SliderRow.qml backend.py settings.py manifest.json README.md LICENSE preview.png; do
  install -m 644 "$source_dir/$file" "$staging/$file"
done
omarchy plugin validate "$staging"
stamp="$(date +%Y%m%d-%H%M%S-%N)"
if [[ -f "$config_root/shell.json" ]]; then
  cp -p "$config_root/shell.json" "$state_root/install-backups/shell-$stamp.json"
fi
if [[ -e "$destination" ]]; then
  mv "$destination" "$state_root/install-backups/plugin-$stamp"
fi
mv "$staging" "$destination"
omarchy-shell shell rescanPlugins
omarchy plugin enable "$plugin_id" --section right
echo "Installed Mouse & Touchpad. Open the mouse icon in the Omarchy bar."
