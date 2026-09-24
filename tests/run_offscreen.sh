#!/usr/bin/env bash
# Run the real panel with disposable state and private display/session buses.
set -euo pipefail
test_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$test_root"

if [[ "${1:-}" == --session ]]; then
  : "${OFFSCREEN_SESSION_ROOT:?Missing isolated session}"
  [[ "$XDG_CONFIG_HOME" == "$OFFSCREEN_SESSION_ROOT/config" ]] || exit 2
  accessibility_config=/usr/share/defaults/at-spi2/accessibility.conf
  registry=/usr/lib/at-spi2-registryd
  [[ -r "$accessibility_config" && -x "$registry" ]] || {
    echo 'Missing the Omarchy/Arch AT-SPI runtime.' >&2; exit 2;
  }
  mapfile -t bus < <(dbus-daemon --config-file="$accessibility_config" \
    --address="unix:abstract=pointer-settings-test-$$" --fork --print-address=1 --print-pid=1)
  [[ "${#bus[@]}" -eq 2 && "${bus[1]}" =~ ^[0-9]+$ ]] || exit 2
  export AT_SPI_BUS_ADDRESS="${bus[0]}"
  registry_pid=""
  cleanup_bus() {
    if [[ -n "$registry_pid" ]]; then
      kill "$registry_pid" 2>/dev/null || true
      wait "$registry_pid" 2>/dev/null || true
    fi
    kill "${bus[1]}" 2>/dev/null || true
  }
  trap cleanup_bus EXIT
  dbus-update-activation-environment AT_SPI_BUS_ADDRESS
  "$registry" --use-gnome-session > "$OFFSCREEN_ARTIFACT_DIR/atspi.log" 2>&1 &
  registry_pid=$!
  ready=0
  for _attempt in {1..50}; do
    if gdbus call --address "$AT_SPI_BUS_ADDRESS" --dest org.a11y.atspi.Registry \
      --object-path /org/a11y/atspi/cache --method org.a11y.atspi.Cache.GetItems >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 0.1
  done
  [[ "$ready" -eq 1 ]] || { echo 'Private accessibility bus did not start.' >&2; exit 2; }
  bash tests/run_ui_smoke.sh
  exit
fi

[[ "$#" -eq 0 ]] || { echo 'Usage: bash tests/run_offscreen.sh' >&2; exit 2; }
for executable in xvfb-run dbus-run-session dbus-daemon dbus-update-activation-environment gdbus qs uv rg; do
  command -v "$executable" >/dev/null || { echo "Missing dependency: $executable" >&2; exit 2; }
done
mkdir -p "$test_root/tmp"
artifacts="$(mktemp -d "$test_root/tmp/ui.XXXXXX")"
session="$artifacts/session"
mkdir -p "$session"/{config,data,state,cache,runtime}
chmod 700 "$session" "$session/runtime"
# Short socket paths are necessary when the checkout is inside a deep worktree.
runtime_container="$(mktemp -d /tmp/pointer-settings-test.XXXXXX)"
ln -s "$session/runtime" "$runtime_container/runtime"
mkdir "$runtime_container/tmp"
cleanup_runtime() {
  mv "$runtime_container/tmp" "$artifacts/tmp"
  unlink "$runtime_container/runtime"
  rmdir "$runtime_container"
}
trap cleanup_runtime EXIT
echo "UI evidence: $artifacts"
env -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u DISPLAY -u XAUTHORITY \
  -u DBUS_SESSION_BUS_ADDRESS -u DBUS_SESSION_BUS_PID -u AT_SPI_BUS_ADDRESS \
  OFFSCREEN_ARTIFACT_DIR="$artifacts" OFFSCREEN_SESSION_ROOT="$session" \
  XDG_CONFIG_HOME="$session/config" XDG_DATA_HOME="$session/data" \
  XDG_STATE_HOME="$session/state" XDG_CACHE_HOME="$session/cache" \
  XDG_RUNTIME_DIR="$runtime_container/runtime" TMPDIR="$runtime_container/tmp" \
  QT_QPA_PLATFORM=xcb GDK_BACKEND=x11 GIO_USE_VFS=local \
  xvfb-run -a -s '-screen 0 1024x768x24' \
  dbus-run-session -- bash "$0" --session > "$artifacts/session.log" 2>&1 || {
    cat "$artifacts/session.log" >&2
    exit 1
  }
cat "$artifacts/session.log"
