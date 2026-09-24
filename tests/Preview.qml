import QtQuick
import Quickshell
import qs.Commons
import ".." as Plugin

Scope {
  id: test
  property int stage: 0
  property int initialTicks: 0
  property real settledAt: 0

  function fail(message) {
    console.error("SMOKE_FAILED: " + message)
    Qt.exit(1)
  }

  FloatingWindow {
    id: window
    visible: true
    title: "Pointer settings — isolated verification"
    implicitWidth: 460
    implicitHeight: view.implicitHeight + 48
    color: Color.background

    Rectangle {
      id: canvas
      anchors.fill: parent
      color: Color.background
      Plugin.SettingsView {
        id: view
        x: 24
        y: 24
        width: window.width - 48
        Component.onCompleted: request("status")
      }
    }
  }

  Timer {
    interval: 50
    repeat: true
    running: true
    onTriggered: {
      if (!view.ready) return
      if (view.failed && test.stage !== 6 && test.stage !== 7) {
        test.fail(view.status)
        return
      }
      // Deliberately edit during the first slow save to catch lost updates.
      if (test.stage === 2 && view.busy && view.action === "apply") {
        view.edit("mouse", 0.12)
        view.edit("touchpad", 0.5)
        test.stage = 3
      }
      if (view.busy) return
      if (test.stage === 0) {
        if (view.draft.mouse !== 0.2 || view.dirty || view.snapshot.canUndo) {
          test.fail("opening the panel changed settings")
          return
        }
        if (++test.initialTicks < 12) return
        test.stage = 1
        canvas.grabToImage(result => {
          result.saveToFile(Quickshell.env("OFFSCREEN_ARTIFACT_DIR") + "/pointer-settings.png")
          console.log("SCREENSHOT_READY")
        })
      } else if (test.stage === 1) {
        view.edit("mouse", 0.1)
        view.edit("touchpad", 0.45)
        if (!view.dirty) test.fail("edits did not become pending")
        test.stage = 2
      } else if (test.stage === 3 && !view.dirty) {
        if (!view.snapshot.canUndo || view.draft.mouse !== 0.12 || view.draft.touchpad !== 0.5) {
          test.fail("edits during a save were lost")
          return
        }
        test.stage = 4
        view.edit("mouse", 0.18)
        view.request("undo")
      } else if (test.stage === 4) {
        if (view.dirty || view.snapshot.canUndo || view.draft.mouse !== 0.1 || view.draft.touchpad !== 0.45) {
          test.fail("undo was overwritten by automatic apply")
          return
        }
        if (test.settledAt === 0) test.settledAt = Date.now()
        if (Date.now() - test.settledAt < 700) return
        view.edit("mouse", 0.2)
        view.edit("touchpad", 0.3771283355)
        test.stage = 5
      } else if (test.stage === 5 && !view.dirty) {
        if (view.draft.mouse !== 0.2) { test.fail("automatic restore failed"); return }
        // The fake compositor rejects this one value and accepts the rollback.
        view.edit("mouse", 0.9)
        test.stage = 6
      } else if (test.stage === 6 && view.failed) {
        test.settledAt = Date.now()
        test.stage = 7
      } else if (test.stage === 7) {
        if (!view.failed || !view.dirty) { test.fail("failed save silently retried"); return }
        if (Date.now() - test.settledAt < 700) return
        test.stage = 8
        view.request("status")
      } else if (test.stage === 8) {
        if (view.failed || view.dirty || view.draft.mouse !== 0.2) {
          test.fail("reload did not recover after the rejected save")
          return
        }
        console.log("SMOKE_PASSED: debounce, queued edits, undo and failed-save recovery")
        Qt.exit(0)
      }
    }
  }
  Timer {
    interval: 15000
    running: true
    onTriggered: test.fail("timeout")
  }
}
