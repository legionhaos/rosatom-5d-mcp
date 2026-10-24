import QtQuick 2.7

// One line of the analysis/apply checklist. The status label has a fixed
// width and is anchored to the right edge, so long labels never push it out.
Item {
    id: root
    property string label: ""
    property string status: "wait"
    property color inkColor: "#263746"
    property color mutedColor: "#748694"
    property color primaryColor: "#147db8"
    property color successColor: "#159a68"
    height: 36

    StepIcon {
        id: icon
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        status: root.status
        activeColor: root.primaryColor
        doneColor: root.successColor
    }

    Text {
        anchors.left: icon.right
        anchors.leftMargin: 10
        anchors.right: statusText.left
        anchors.rightMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: root.label
        color: root.status === "wait" ? root.mutedColor : root.inkColor
        font.pixelSize: 11
        font.bold: root.status === "active"
        elide: Text.ElideRight
    }

    Text {
        id: statusText
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 84
        horizontalAlignment: Text.AlignRight
        text: root.status === "done" ? "готово" : (root.status === "active" ? "выполняется" : "ожидание")
        color: root.status === "done" ? root.successColor : (root.status === "active" ? root.primaryColor : root.mutedColor)
        font.pixelSize: 10
    }

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: "#eef3f6"
    }
}
