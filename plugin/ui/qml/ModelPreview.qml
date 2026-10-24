import QtQuick 2.7
import QtQuick.Controls 1.4

// Snapshot of the STE Slicer build plate rendered by ChatController.refreshPreview().
// It updates automatically when the scene changes (load, rotate, scale).
Rectangle {
    id: root
    property var controller: null
    readonly property string source: controller ? controller.previewUrl : ""
    color: "#f2f8fb"
    border.color: "#d5e1e8"
    clip: true

    Image {
        id: image
        anchors.fill: parent
        anchors.margins: 8
        source: root.source
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        cache: false
        smooth: true
        visible: status === Image.Ready
    }

    Column {
        anchors.centerIn: parent
        spacing: 8
        visible: !image.visible
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "◈"; color: "#7ab2cc"; font.pixelSize: 40 }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            width: root.width - 30
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: controller && controller.previewMessage ? controller.previewMessage : "Строим превью модели…"
            color: "#748694"
            font.pixelSize: 11
        }
    }

    Button {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 6
        text: "↻"
        width: 28
        tooltip: "Обновить превью"
        onClicked: if (root.controller) root.controller.refreshPreview()
    }
}
