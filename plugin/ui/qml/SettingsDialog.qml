import QtQuick 2.2
import QtQuick.Controls 1.4

Rectangle {
    id: root
    color: "#550e1a23"
    property var controller

    Rectangle {
        id: dialog
        width: 490
        height: 380
        anchors.centerIn: parent
        radius: 10
        color: "#ffffff"
        border.color: "#d4e1e8"

        Column {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 13
            Row {
                width: parent.width
                Label { text: "Настройки AI"; color: "#263746"; font.pixelSize: 18; font.bold: true }
                Item { width: parent.width - 160; height: 1 }
                ToolButton { text: "×"; onClicked: root.visible = false }
            }
            Label { text: "OpenAI-совместимый API"; color: "#708391"; font.pixelSize: 11 }
            Label { text: "Base URL"; color: "#263746"; font.pixelSize: 11 }
            TextField { id: baseUrl; width: parent.width; placeholderText: "https://api.example.com/v1"; text: "" }
            Label { text: "API Key"; color: "#263746"; font.pixelSize: 11 }
            TextField { id: apiKey; width: parent.width; placeholderText: "Введите ключ доступа"; echoMode: TextInput.Password; text: "" }
            Label { text: "Модель"; color: "#263746"; font.pixelSize: 11 }
            TextField { id: modelName; width: parent.width; placeholderText: "Название модели"; text: "" }
            Row {
                spacing: 8
                Button { text: "Проверить соединение"; onClicked: if (controller) controller.checkConnection(baseUrl.text, apiKey.text, modelName.text) }
                Button { text: "Сохранить"; onClicked: { if (controller) controller.saveSettings(baseUrl.text, apiKey.text, modelName.text); root.visible = false } }
                Button { text: "Отмена"; onClicked: root.visible = false }
            }
            Label { text: "Ключ хранится в настройках приложения и не выводится в лог."; color: "#82939e"; font.pixelSize: 10; wrapMode: Text.Wrap; width: parent.width }
        }
    }
}
