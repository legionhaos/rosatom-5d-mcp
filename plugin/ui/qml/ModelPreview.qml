import QtQuick 2.7

// Static standard-angle X-ray-style preview. The image is intentionally not interactive.
Rectangle {
    id: root
    property var controller: null
    readonly property string source: controller ? controller.previewUrl : ""
    readonly property bool hasModel: controller && controller.modelCount > 0
    readonly property string dimsText: controller && controller.dimensionsText ? controller.dimensionsText : ""

    color: "#111827"
    radius: 10
    border.color: "#334155"
    border.width: 1
    clip: true

    Item {
        id: previewStage
        anchors.fill: parent
        anchors.margins: 4
        visible: root.hasModel && previewImage.status === Image.Ready

        Image {
            id: previewImage
            anchors.fill: parent
            source: root.source
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: false
            smooth: true
            opacity: 0.92
        }

    }

    Image {
        id: previewStatusImage
        visible: false
        source: root.source
        asynchronous: true
        cache: false
    }

    Rectangle {
        anchors.fill: previewImage
        color: "transparent"
        border.color: "#67e8f9"
        border.width: 1
        opacity: 0.18
        visible: previewImage.visible
    }

    Row {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 10
        spacing: 8
        visible: previewImage.visible

        Rectangle {
            height: 24
            width: xrayLabel.implicitWidth + 18
            radius: 12
            color: "#164e63"
            border.color: "#67e8f9"
            border.width: 1
            Text {
                id: xrayLabel
                anchors.centerIn: parent
                text: "◉ Рентген-превью"
                color: "#cffafe"
                font.pixelSize: 10
                font.bold: true
            }
        }

        Rectangle {
            height: 24
            width: dimensionsLabel.implicitWidth + 18
            radius: 12
            color: "#1e293b"
            border.color: "#475569"
            border.width: 1
            visible: root.dimsText.length > 0
            Text {
                id: dimensionsLabel
                anchors.centerIn: parent
                text: root.dimsText
                color: "#e2e8f0"
                font.pixelSize: 10
                font.bold: true
            }
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: 10
        visible: !previewImage.visible

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.hasModel ? "Строится рентген-превью…" : "Модель не загружена"
            color: "#e2e8f0"
            font.pixelSize: 13
            font.bold: true
        }
        Text {
            width: Math.min(root.width - 40, 300)
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: root.hasModel && controller ? controller.previewMessage : "Загрузите STL/OBJ/3MF в STE Slicer"
            color: "#94a3b8"
            font.pixelSize: 11
        }
    }
}
