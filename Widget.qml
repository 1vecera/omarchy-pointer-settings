import QtQuick
import QtQuick.Controls as Controls
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "daniel.pointer-settings"
  ipcTarget: "daniel.pointer-settings"
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: {
    if (opened) {
      if (!settingsView.busy && !settingsView.dirty) settingsView.request("status")
      Qt.callLater(() => settingsView.forceActiveFocus())
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰍽"
    tooltipText: "Mouse & Touchpad"
    onPressed: mouseButton => { if (mouseButton === Qt.LeftButton) root.toggle() }
  }

  KeyboardPanel {
    id: popup
    anchorItem: button
    bar: root.bar
    owner: root
    open: root.opened
    focusTarget: settingsView
    contentWidth: fittedContentWidth(Style.space(390))
    contentHeight: fittedContentHeight(settingsView.implicitHeight)

    Controls.ScrollView {
      anchors.fill: parent
      clip: true
      contentWidth: availableWidth
      Controls.ScrollBar.horizontal.policy: Controls.ScrollBar.AlwaysOff
      SettingsView {
        id: settingsView
        width: parent.width
        Keys.onEscapePressed: root.close()
      }
    }
  }
}
