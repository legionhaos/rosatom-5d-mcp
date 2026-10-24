import QtQuick 2.7

Rectangle {
    id: root
    property real value: 0
    property bool busy: false
    property color barColor: "#2563eb"
    height: 8
    radius: 4
    color: "#e2e8f0"
    clip: true

    Rectangle {
        id: fill
        height: parent.height
        radius: 4
        color: root.barColor
        width: parent.width * Math.max(0.04, Math.min(1.0, root.value))
        Behavior on width { NumberAnimation { duration: 350; easing.type: Easing.OutCubic } }
    }

    Rectangle {
        id: shine
        visible: root.busy
        height: parent.height
        width: 70
        radius: 4
        color: "#ffffff"
        opacity: 0.55
        NumberAnimation on x {
            from: -70
            to: fill.width
            duration: 1200
            loops: Animation.Infinite
            running: root.busy
        }
    }
}
