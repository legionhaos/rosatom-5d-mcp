import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Dialogs 1.2
import QtQuick.Layouts 1.1

Rectangle {
    id: root
    height: (attachmentModel && attachmentModel.rowCount() > 0) ? (attachCol.implicitHeight + 10) : 46
    color: "transparent"
    property var controller: (typeof chatController !== "undefined" && chatController) ? chatController : null
    property var attachmentModel: null

    readonly property var activeCtrl: (typeof controller !== "undefined" && controller) ? controller : (typeof chatController !== "undefined" ? chatController : null)

    FileDialog {
        id: fileDialog
        title: "Выберите 3D-модель или изображение с нагрузкой"
        selectMultiple: true
        nameFilters: [
            "3D-модели (*.stl *.obj *.3mf)",
            "Изображения (*.png *.jpg *.jpeg)",
            "Все поддерживаемые файлы (*.stl *.obj *.3mf *.png *.jpg *.jpeg)"
        ]
        onAccepted: {
            if (activeCtrl) {
                for (var i = 0; i < fileUrls.length; i++) {
                    activeCtrl.addAttachment(fileUrls[i].toString())
                }
            }
        }
    }

    Column {
        id: attachCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 20
        anchors.rightMargin: 16
        spacing: 8

        // Attached Files Chips Flow
        Flow {
            width: parent.width
            spacing: 8
            visible: attachmentModel && attachmentModel.rowCount() > 0

            Repeater {
                model: root.attachmentModel
                delegate: Rectangle {
                    height: 32
                    radius: 16
                    color: model.kind === "image" ? "#fef3c7" : "#e0f2fe"
                    border.color: model.kind === "image" ? "#fde68a" : "#bae6fd"
                    border.width: 1
                    implicitWidth: chipRow.width + 12

                    Row {
                        id: chipRow
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        spacing: 6

                        // Kind Icon
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: model.kind === "image" ? "🖼" : "🧊"
                            font.pixelSize: 13
                        }

                        // File Name
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: model.name || "файл"
                            color: "#0f172a"
                            font.pixelSize: 11
                            font.weight: Font.Medium
                            maximumLineCount: 1
                            elide: Text.ElideMiddle
                            width: Math.min(implicitWidth, 140)
                        }

                        // Size badge
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            height: 18
                            radius: 9
                            color: "#ffffff"
                            border.color: "#cbd5e1"
                            border.width: 1
                            implicitWidth: sizeLabel.width + 8

                            Text {
                                id: sizeLabel
                                anchors.centerIn: parent
                                text: model.sizeText || ""
                                font.pixelSize: 9
                                color: "#64748b"
                            }
                        }

                        // =====================================================
                        // PROMINENT CLOSE / REMOVE BUTTON (✕) ON EACH CHIP
                        // =====================================================
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 20
                            height: 20
                            radius: 10
                            color: removeChipMouse.containsMouse ? "#fee2e2" : "transparent"

                            Text {
                                anchors.centerIn: parent
                                text: "✕"
                                font.pixelSize: 10
                                font.bold: true
                                color: removeChipMouse.containsMouse ? "#ef4444" : "#64748b"
                            }

                            MouseArea {
                                id: removeChipMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (activeCtrl && activeCtrl.removeAttachment) {
                                        activeCtrl.removeAttachment(index)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Attach Button & Drag & Drop Area
        RowLayout {
            width: parent.width
            spacing: 10

            // Attach Button
            Rectangle {
                width: 154
                height: 36
                radius: 8
                color: attachBtnMouse.containsMouse ? "#e2e8f0" : "#f1f5f9"
                border.color: attachBtnMouse.containsMouse ? "#94a3b8" : "#cbd5e1"
                border.width: 1

                Row {
                    anchors.centerIn: parent
                    spacing: 6
                    Text { text: "📎"; font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: "Прикрепить файл"
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        color: "#1e293b"
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                MouseArea {
                    id: attachBtnMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: fileDialog.open()
                }
            }

            // Drag and Drop Zone
            Rectangle {
                Layout.fillWidth: true
                height: 36
                radius: 8
                color: dropArea.containsDrag ? "#eff6ff" : "#f8fafc"
                border.color: dropArea.containsDrag ? "#1976d2" : "#e2e8f0"
                border.width: dropArea.containsDrag ? 2 : 1

                Row {
                    anchors.centerIn: parent
                    spacing: 6
                    Text {
                        text: dropArea.containsDrag ? "📥" : "💡"
                        font.pixelSize: 12
                    }
                    Text {
                        text: dropArea.containsDrag ? "Отпустите файлы для добавления" : "Перетащите STL, OBJ, 3MF или фото нагрузок сюда"
                        color: dropArea.containsDrag ? "#1976d2" : "#64748b"
                        font.pixelSize: 11
                    }
                }

                DropArea {
                    id: dropArea
                    anchors.fill: parent
                    onDropped: {
                        if (drop.hasUrls && activeCtrl) {
                            for (var i = 0; i < drop.urls.length; i++) {
                                activeCtrl.addAttachment(drop.urls[i].toString())
                            }
                        }
                    }
                }
            }
        }
    }
}
