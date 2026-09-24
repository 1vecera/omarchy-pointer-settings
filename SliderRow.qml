import QtQuick
import qs.Commons
import qs.Ui

Column {
  id: root
  property string label: ""
  property real value: 0
  property real minimum: 0
  property real maximum: 2
  property real step: 0.05
  property bool multiplier: false
  signal edited(real value)
  spacing: Style.spacing.sm
  opacity: enabled ? 1 : 0.45

  Row {
    width: parent.width
    Text {
      width: parent.width - valueLabel.width
      text: root.label
      textFormat: Text.PlainText
      color: Color.foreground
      font.family: Style.font.family
      font.pixelSize: Style.font.body
    }
    Text {
      id: valueLabel
      text: root.value.toFixed(2) + (root.multiplier ? "×" : "")
      textFormat: Text.PlainText
      color: Color.accent
      font.family: Style.font.family
      font.pixelSize: Style.font.body
    }
  }

  PanelSlider {
    id: slider
    width: parent.width
    value: root.value
    minimum: root.minimum
    maximum: root.maximum
    step: root.step
    activeFocusOnTab: true
    Accessible.role: Accessible.Slider
    Accessible.name: root.label
    Accessible.description: "Use left and right arrows to adjust"
    Keys.onLeftPressed: root.edited(Math.max(root.minimum, root.value - root.step))
    Keys.onRightPressed: root.edited(Math.min(root.maximum, root.value + root.step))
    Keys.onPressed: event => {
      if (event.key === Qt.Key_Home || event.key === Qt.Key_End) {
        root.edited(event.key === Qt.Key_Home ? root.minimum : root.maximum)
        event.accepted = true
      }
    }
    onMoved: value => root.edited(Math.round(value * 100) / 100)

    Rectangle {
      anchors.fill: parent
      anchors.margins: -Style.space(3)
      color: "transparent"
      border.color: Color.accent
      border.width: slider.activeFocus ? 1 : 0
      radius: Style.cornerRadius
    }
  }
}
