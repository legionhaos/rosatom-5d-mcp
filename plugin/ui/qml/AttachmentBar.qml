import QtQuick 2.2
import QtQuick.Controls 1.4
import QtQuick.Dialogs 1.2
import QtQuick.Layouts 1.1

Rectangle {
    id: root
    height: attachmentModel && attachmentModel.rowCount() > 0 ? 58 : 44
    color: "transparent"
    property var controller
    property var attachmentModel

    FileDialog {
        id: fileDialog
        title: "Выберите модель или изображение"
        selectMultiple: true
        nameFilters: ["3D-модели (*.stl *.obj *.3mf)", "Изображения (*.png *.jpg *.jpeg)", "Все поддерживаемые файлы (*.stl *.obj *.3mf *.png *.jpg *.jpeg)"]
        onAccepted: {
            for (var i = 0; i < fileUrls.length; i++) controller.addAttachment(fileUrls[i].toString())
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 18
        anchors.rightMargin: 18
        spacing: 8
        Button { text: "＋ Прикрепить файл"; onClicked: fileDialog.open(); enabled: controller !== null }
        Rectangle {
            Layout.fillWidth: true
            height: 34
            color: dropArea.containsDrag ? "#e3f4fb" : "#f8fbfd"
            border.color: dropArea.containsDrag ? "#147db8" : "#d5e1e8"
            radius: 6
            Label { anchors.centerIn: parent; text: dropArea.containsDrag ? "Отпустите файл" : "или перетащите STL / OBJ / 3MF / PNG / JPG сюда"; color: "#7b8e9c"; font.pixelSize: 10 }
            DropArea {
                id: dropArea
                anchors.fill: parent
                onDropped: {
                    if (drop.hasUrls) {
                        for (var i = 0; i < drop.urls.length; i++) controller.addAttachment(drop.urls[i].toString())
                    }
                }
            }
        }
    }

    Flow {
        anchors.left: parent.left
        anchors.leftMargin: 18
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 6
        Repeater {
            model: attachmentModel
            delegate: Rectangle {
                width: 190; height: 28; radius: 5; color: "#e8f5fa"; border.color: "#c6e4ef"
                Row {
                    anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 5; spacing: 5
                    Label { anchors.verticalCenter: parent.verticalCenter; text: model.kind === "image" ? "▧" : "◈"; color: "#147db8" }
                    Label { anchors.verticalCenter: parent.verticalCenter; text: model.name; width: 135; elide: Text.ElideMiddle; color: "#365466"; font.pixelSize: 10 }
                    ToolButton { text: "×"; anchors.verticalCenter: parent.verticalCenter; onClicked: controller.removeAttachment(index) }
                }
            }
        }
    }
}
