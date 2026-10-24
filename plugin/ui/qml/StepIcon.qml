import QtQuick 2.7

Item {
    id: root
    property string status: "wait" // "wait", "active", "done", "error"
    property color activeColor: "#2563eb"
    property color doneColor: "#10b981"
    property color idleColor: "#94a3b8"
    property color errorColor: "#ef4444"
    width: 20
    height: 20

    // Wait state
    Rectangle {
        anchors.centerIn: parent
        width: 12
        height: 12
        radius: 6
        color: "transparent"
        border.color: root.idleColor
        border.width: 1.5
        visible: root.status === "wait"
    }

    // Done state
    Rectangle {
        anchors.centerIn: parent
        width: 18
        height: 18
        radius: 9
        color: "#ecfdf5"
        border.color: root.doneColor
        border.width: 1.5
        visible: root.status === "done"

        Text {
            anchors.centerIn: parent
            text: "✓"
            color: root.doneColor
            font.pixelSize: 11
            font.bold: true
        }
    }

    // Error state
    Rectangle {
        anchors.centerIn: parent
        width: 18
        height: 18
        radius: 9
        color: "#fef2f2"
        border.color: root.errorColor
        border.width: 1.5
        visible: root.status === "error" || root.status === "err"

        Text {
            anchors.centerIn: parent
            text: "!"
            color: root.errorColor
            font.pixelSize: 11
            font.bold: true
        }
    }

    // Active spinner
    Canvas {
        id: spinner
        anchors.fill: parent
        visible: root.status === "active"
        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();
            ctx.lineWidth = 2.5;
            ctx.lineCap = "round";

            // Track
            ctx.strokeStyle = "#e2e8f0";
            ctx.beginPath();
            ctx.arc(width / 2, height / 2, width / 2 - 3, 0, 2 * Math.PI);
            ctx.stroke();

            // Head
            ctx.strokeStyle = root.activeColor;
            ctx.beginPath();
            ctx.arc(width / 2, height / 2, width / 2 - 3, 0, Math.PI * 1.2);
            ctx.stroke();
        }

        RotationAnimation on rotation {
            from: 0
            to: 360
            duration: 850
            loops: Animation.Infinite
            running: spinner.visible
        }
    }
}
