#!/usr/bin/env bash
set -euo pipefail
test_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
: "${OFFSCREEN_ARTIFACT_DIR:?Run this through tests/run_offscreen.sh or an isolated harness}"
: "${OFFSCREEN_SESSION_ROOT:?Missing isolated session}"
[[ "$XDG_CONFIG_HOME" == "$OFFSCREEN_SESSION_ROOT"/* ]] || exit 2
mkdir -p "$XDG_CONFIG_HOME/hypr" "$OFFSCREEN_ARTIFACT_DIR/bin" "$OFFSCREEN_ARTIFACT_DIR/qml"
cp "$test_root/tests/fixtures/input.lua" "$XDG_CONFIG_HOME/hypr/input.lua"
cat > "$OFFSCREEN_ARTIFACT_DIR/bin/hyprctl" <<'EOF'
#!/bin/sh
case "$1" in
  reload) sleep 0.35; echo reload >> "$OFFSCREEN_ARTIFACT_DIR/reloads"; echo ok ;;
  configerrors)
    if rg -q 'sensitivity = 0.9,' "$XDG_CONFIG_HOME/hypr/input.lua"; then
      echo 'Synthetic rejected setting'
    fi
    ;;
  getoption) echo 'int: 0' ;;
  *) echo "Unexpected test command: $*" >&2; exit 1 ;;
esac
EOF
chmod +x "$OFFSCREEN_ARTIFACT_DIR/bin/hyprctl"
ln -s /usr/share/omarchy/shell/Commons "$OFFSCREEN_ARTIFACT_DIR/qml/Commons"
ln -s /usr/share/omarchy/shell/Ui "$OFFSCREEN_ARTIFACT_DIR/qml/Ui"
ln -s "$test_root" "$OFFSCREEN_ARTIFACT_DIR/qml/plugin"
sed 's|import ".." as Plugin|import "plugin" as Plugin|' "$test_root/tests/Preview.qml" > "$OFFSCREEN_ARTIFACT_DIR/qml/shell.qml"
export PATH="$OFFSCREEN_ARTIFACT_DIR/bin:$PATH"
export POINTER_SETTINGS_HYPRCTL="$OFFSCREEN_ARTIFACT_DIR/bin/hyprctl"
unset HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY
export QT_QPA_PLATFORM=xcb QT_QUICK_BACKEND=software QT_SCALE_FACTOR=1 GDK_SCALE=1 QT_QPA_PLATFORMTHEME=generic
timeout 25 qs -p "$OFFSCREEN_ARTIFACT_DIR/qml" --no-color > "$OFFSCREEN_ARTIFACT_DIR/ui.log" 2>&1
cmp "$test_root/tests/fixtures/input.lua" "$XDG_CONFIG_HOME/hypr/input.lua"
[[ "$(wc -l < "$OFFSCREEN_ARTIFACT_DIR/reloads")" -eq 6 ]]
rg 'SMOKE_PASSED' "$OFFSCREEN_ARTIFACT_DIR/ui.log"
if rg 'SMOKE_FAILED|ReferenceError|TypeError|Error loading|Cannot assign|Unable to assign|Binding loop' "$OFFSCREEN_ARTIFACT_DIR/ui.log"; then
  exit 1
fi
