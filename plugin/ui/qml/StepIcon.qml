import QtQuick 2.7

// Step status icon: "wait" (empty circle), "active" (spinning arc), "done" (check mark).
Item {
    id: root
    property string status: "wait"
    property string activeColor: "#147db8"
    property string doneColor: "#159a68"
    property string idleColor: "#a5b4be"
    width: 18
    height: 18

    Rectangle {
        anchors.centerIn: parent
        width: 11
        height: 11
        radius: 6
        color: "transparent"
        border.color: root.idleColor
        border.width: 1.5
        visible: root.status === "wait"
    }

    Text {
        anchors.centerIn: parent
        text: "✓"
        color: root.doneColor
        font.pixelSize: 14
        font.bold: true
        visible: root.status === "done"
    }

    Canvas {
        id: spinner
        anchors.fill: parent
        visible: root.status === "active"
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.lineWidth = 2
            ctx.lineCap = "round"
            ctx.strokeStyle = "#dbe8ef"
            ctx.beginPath()
            ctx.arc(width / 2, height / 2, width / 2 - 2, 0, 2 * Math.PI)
            ctx.stroke()
            ctx.strokeStyle = root.activeColor
            ctx.beginPath()
            ctx.arc(width / 2, height / 2, width / 2 - 2, 0, Math.PI * 1.3)
            ctx.stroke()
        }
        RotationAnimation on rotation {
            from: 0
            to: 360
            duration: 900
            loops: Animation.Infinite
            running: spinner.visible
        }
    }
}
