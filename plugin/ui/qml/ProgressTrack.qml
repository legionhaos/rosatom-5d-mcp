import QtQuick 2.7

// Progress bar with a moving highlight while the agent is busy, so the
// window never looks frozen between tool calls.
Rectangle {
    id: root
    property real value: 0
    property bool busy: false
    property color barColor: "#147db8"
    height: 6
    radius: 3
    color: "#e7eef2"
    clip: true

    Rectangle {
        id: fill
        height: parent.height
        radius: 3
        color: root.barColor
        width: parent.width * Math.max(0.06, Math.min(1, root.value))
        Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
    }

    Rectangle {
        id: shine
        visible: root.busy
        height: parent.height
        width: 60
        radius: 3
        color: "#ffffff"
        opacity: 0.45
        NumberAnimation on x {
            from: -60
            to: fill.width
            duration: 1300
            loops: Animation.Infinite
            running: root.busy
        }
    }
}
