import QtQuick 2.7

Item {
    id: root
    property string label: ""
    property string status: "wait"
    property color inkColor: "#0f172a"
    property color mutedColor: "#64748b"
    property color primaryColor: "#2563eb"
    property color successColor: "#10b981"
    property color errorColor: "#ef4444"
    height: 40

    Rectangle {
        anchors.fill: parent
        color: root.status === "active" ? "#eff6ff" : "transparent"
        radius: 6

        StepIcon {
            id: icon
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            status: root.status
            activeColor: root.primaryColor
            doneColor: root.successColor
            errorColor: root.errorColor
        }

        Text {
            anchors.left: icon.right
            anchors.leftMargin: 12
            anchors.right: statusPill.left
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            text: root.label
            color: root.status === "wait" ? root.mutedColor : root.inkColor
            font.pixelSize: 12
            font.bold: root.status === "active"
            elide: Text.ElideRight
        }

        Rectangle {
            id: statusPill
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            height: 22
            radius: 11
            implicitWidth: statusText.width + 16
            color: root.status === "done" ? "#ecfdf5" : (root.status === "active" ? "#dbeafe" : "#f1f5f9")
            border.color: root.status === "done" ? "#a7f3d0" : (root.status === "active" ? "#bfdbfe" : "#e2e8f0")
            border.width: 1

            Text {
                id: statusText
                anchors.centerIn: parent
                text: root.status === "done" ? "готово" : (root.status === "active" ? "в процессе" : "ожидание")
                color: root.status === "done" ? "#065f46" : (root.status === "active" ? "#1d4ed8" : "#64748b")
                font.pixelSize: 10
                font.bold: root.status === "active" || root.status === "done"
            }
        }

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: "#f1f5f9"
        }
    }
}
