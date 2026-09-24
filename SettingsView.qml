import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui

Column {
  id: root
  property var snapshot: null
  property var draft: ({mouse: 0, mouse_scroll: 1, touchpad: 1, touchpad_scroll: 1})
  property string status: "Loading settings…"
  property bool failed: false
  property string action: "status"
  property int editSerial: 0
  property int sentSerial: 0
  readonly property bool busy: helper.running
  readonly property bool dirty: snapshot !== null && JSON.stringify(draft) !== JSON.stringify(snapshot.values)
  readonly property bool ready: snapshot !== null
  property alias helperProcess: helper
  spacing: Style.spacing.lg

  function request(action) {
    if (busy) return
    autoApply.stop()
    root.action = action
    root.sentSerial = root.editSerial
    root.failed = false
    root.status = action === "status" ? "Loading settings…" : "Applying settings…"
    const script = decodeURIComponent(Qt.resolvedUrl("settings.py").toString().replace(/^file:\/\//, ""))
    helper.command = ["uv", "run", "--no-project", "--no-config", "--python", "/usr/bin/python", "python", "-B", script, action,
                      JSON.stringify({revision: snapshot ? snapshot.revision : "", values: draft})]
    helper.running = true
  }

  function edit(key, value) {
    if (!ready || draft[key] === value) return
    const next = Object.assign({}, draft)
    next[key] = value
    draft = next
    editSerial += 1
    failed = false
    status = dirty ? "Applying automatically…" : "Changes apply automatically."
    autoApply.restart()
  }

  function accept(text) {
    try {
      const result = JSON.parse(text)
      if (!result.ok) throw new Error(result.error)
      const newerEdits = action === "apply" && editSerial !== sentSerial
      snapshot = result.state
      if (!newerEdits) draft = Object.assign({}, snapshot.values)
      failed = false
      status = dirty ? "Applying automatically…"
             : action === "apply" ? "Saved automatically. Undo is available."
             : action === "undo" ? "Previous settings restored."
             : "Changes apply automatically."
      if (dirty) autoApply.restart()
    } catch (error) {
      autoApply.stop()
      failed = true
      status = String(error.message || error)
    }
  }

  Timer {
    id: autoApply
    interval: 300
    onTriggered: {
      if (root.ready && root.dirty && !root.busy && !root.failed) root.request("apply")
    }
  }

  Process {
    id: helper
    stdout: StdioCollector {
      id: output
      waitForEnd: true
      onStreamFinished: root.accept(text)
    }
    stderr: StdioCollector { id: errors; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode !== 0 && String(output.text).trim() === "") {
        root.failed = true
        root.status = "Could not start settings helper. Check that uv and Python are installed. " + errors.text
      }
      if (!root.failed && root.dirty && root.action === "apply") autoApply.restart()
    }
  }

  Text {
    width: parent.width
    text: "Mouse & Touchpad"
    textFormat: Text.PlainText
    font.family: Style.font.family
    font.pixelSize: Style.font.title
    font.bold: true
    color: Color.foreground
  }

  Column {
    width: parent.width
    spacing: Style.spacing.md
    enabled: root.ready && (!root.busy || root.action === "apply")
    PanelSectionHeader { text: "MOUSE & TRACKPOINT" }
    SliderRow {
      objectName: "mouseSensitivity"
      width: parent.width
      label: "Pointer sensitivity"
      value: root.draft.mouse
      minimum: -1
      maximum: 1
      onEdited: value => root.edit("mouse", value)
    }
    SliderRow {
      width: parent.width
      label: "Wheel scroll speed"
      value: root.draft.mouse_scroll
      minimum: 0.1
      multiplier: true
      onEdited: value => root.edit("mouse_scroll", value)
    }
  }

  PanelSeparator { width: parent.width }

  Column {
    width: parent.width
    spacing: Style.spacing.md
    visible: root.snapshot === null || root.snapshot.hasTouchpad
    enabled: root.ready && (!root.busy || root.action === "apply")
    PanelSectionHeader { text: "TOUCHPAD" }
    SliderRow {
      objectName: "touchpadSensitivity"
      width: parent.width
      label: "Pointer speed"
      value: root.draft.touchpad
      minimum: root.snapshot && root.snapshot.custom ? 0.05 : -1
      maximum: root.snapshot && root.snapshot.custom ? 2 : 1
      multiplier: root.snapshot !== null && root.snapshot.custom
      onEdited: value => root.edit("touchpad", value)
    }
    SliderRow {
      width: parent.width
      label: "Two-finger scroll speed"
      value: root.draft.touchpad_scroll
      minimum: 0.1
      multiplier: true
      onEdited: value => root.edit("touchpad_scroll", value)
    }
  }

  Text {
    width: parent.width
    visible: root.snapshot !== null && !root.snapshot.hasTouchpad
    text: "No touchpad detected."
    color: Color.foreground
    opacity: 0.75
    font.family: Style.font.family
    font.pixelSize: Style.font.caption
  }

  Text {
    width: parent.width
    text: root.status
    textFormat: Text.PlainText
    wrapMode: Text.Wrap
    color: root.failed ? Color.urgent : Color.foreground
    opacity: root.failed ? 1 : 0.75
    font.family: Style.font.family
    font.pixelSize: Style.font.caption
    Accessible.role: Accessible.StaticText
    Accessible.name: text
  }

  Row {
    width: parent.width
    spacing: Style.spacing.sm
    Button {
      text: "Reload"
      enabled: !root.busy
      focusable: true
      bordered: true
      onClicked: root.request("status")
    }
    Button {
      text: "Undo"
      enabled: !root.busy && root.snapshot !== null && root.snapshot.canUndo
      opacity: enabled ? 1 : 0.4
      focusable: true
      bordered: true
      onClicked: root.request("undo")
    }
  }
}
