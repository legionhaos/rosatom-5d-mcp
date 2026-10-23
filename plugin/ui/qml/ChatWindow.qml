import QtQuick 2.2
import QtQuick.Controls 1.4
import QtQuick.Layouts 1.1

Rectangle {
    id: root
    objectName: "chatWindow"
    width: 1040
    height: 720
    color: "#f3f7fa"

    property color ink: "#263746"
    property color muted: "#708391"
    property color border: "#d5e1e8"
    property color primary: "#147db8"
    property var controller

    function sendCurrentPrompt() {
        var value = promptInput.text.trim()
        if (value.length === 0 || !controller) return
        controller.sendPrompt(value)
        promptInput.text = ""
    }

    Connections {
        target: controller
        onMessageAdded: messageList.positionViewAtEnd()
        onTaskStarted: statusLabel.text = "Агент работает"
        onTaskFinished: statusLabel.text = "Готово"
        onTaskFailed: statusLabel.text = "Ошибка"
        onConnectedChanged: statusLabel.text = controller.connected ? "STE Slicer подключен" : "STE Slicer не подключен"
    }

    Rectangle {
        id: header
        width: parent.width
        height: 62
        color: "white"
        border.color: root.border

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 22
            anchors.rightMargin: 18
            spacing: 14

            Label {
                text: "✣"
                color: root.primary
                font.pixelSize: 28
            }
            Label {
                text: "slicer " + "<b>assistant</b>"
                textFormat: Text.RichText
                color: "#536c7d"
                font.pixelSize: 21
            }
            Item { Layout.fillWidth: true }
            Label { id: statusLabel; text: "Подключение…"; color: root.muted; font.pixelSize: 11 }
            Rectangle { width: 8; height: 8; radius: 4; color: controller && controller.connected ? "#22a06b" : "#d6a33c" }
            Button { text: "Настройки"; onClicked: settings.visible = true }
        }
    }

    Rectangle {
        id: sceneBar
        anchors.top: header.bottom
        width: parent.width
        height: 42
        color: "#edf5f9"
        border.color: root.border
        Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 22
            spacing: 22
            Label { text: "Принтер: " + (controller ? controller.printerName : "—"); color: root.ink; font.pixelSize: 11 }
            Label { text: "Режим: " + (controller ? controller.printMode : "—"); color: root.ink; font.pixelSize: 11 }
            Label { text: "Материал: " + (controller ? controller.material : "—"); color: root.ink; font.pixelSize: 11 }
            Label { text: "Моделей на столе: " + (controller ? controller.modelCount : 0); color: root.ink; font.pixelSize: 11 }
        }
    }

    ColumnLayout {
        anchors.top: sceneBar.bottom
        anchors.bottom: parent.bottom
        width: parent.width
        spacing: 0

        ListView {
            id: messageList
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: 18
            clip: true
            spacing: 9
            model: controller ? controller.messageModel : null

            delegate: Rectangle {
                width: messageList.width - 8
                height: messageColumn.height + 18
                radius: 8
                color: model.kind === "user" ? "#e5f3fb" : (model.kind === "tool_trace" ? "#f7fbfd" : "white")
                border.color: model.kind === "tool_trace" ? "#c4e0ec" : root.border
                anchors.rightMargin: model.kind === "user" ? 8 : 70
                anchors.leftMargin: model.kind === "user" ? 70 : 8

                Column {
                    id: messageColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 9
                    spacing: 5
                    Row {
                        spacing: 7
                        Label { text: model.kind === "user" ? "Вы" : (model.kind === "tool_trace" ? "Инструмент" : "AI assistant"); color: root.primary; font.bold: true; font.pixelSize: 10 }
                        Label { text: model.toolName || model.timestamp; color: root.muted; font.pixelSize: 9 }
                    }
                    Label { visible: model.kind !== "tool_trace"; text: model.text; wrapMode: Text.Wrap; width: parent.width; color: root.ink; font.pixelSize: 12 }
                    Row {
                        visible: model.kind === "tool_trace"
                        spacing: 8
                        Label { text: model.text; color: root.ink; font.pixelSize: 11 }
                        Label { text: model.status === "ok" ? "✓ OK" : (model.status === "err" ? "✕ ERR" : "⟳ PENDING"); color: model.status === "err" ? "#c94b50" : (model.status === "ok" ? "#159a68" : "#b2771f"); font.pixelSize: 10 }
                        Label { text: model.durationMs > 0 ? model.durationMs + " ms" : ""; color: root.muted; font.pixelSize: 9 }
                    }
                    Label { visible: model.kind === "tool_trace" && model.toolArguments.length > 0; text: model.toolArguments; color: root.muted; font.family: "Monospace"; font.pixelSize: 9; wrapMode: Text.Wrap; width: parent.width; maximumLineCount: 4; elide: Text.ElideRight }
                }
            }

            Label {
                anchors.centerIn: parent
                visible: messageList.count === 0
                text: "Опишите задачу печати или прикрепите модель"
                color: root.muted
                font.pixelSize: 14
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 18
            Layout.rightMargin: 18
            spacing: 8
            Repeater {
                model: ["Кронштейн под нагрузку", "Без поддержек", "Подготовить 5D"]
                delegate: Button { text: modelData; onClicked: promptInput.text = modelData }
            }
            Item { Layout.fillWidth: true }
            Button { text: "Лог агента"; onClicked: logDrawer.opened = !logDrawer.opened }
        }

        AttachmentBar { id: attachments; Layout.fillWidth: true; controller: root.controller; attachmentModel: controller ? controller.attachmentModel : null }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 82
            Layout.margins: 18
            color: "white"
            border.color: root.border
            radius: 8
            RowLayout {
                anchors.fill: parent
                anchors.margins: 10
                TextArea {
                    id: promptInput
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    placeholderText: "Опишите задачу печати…"
                    wrapMode: TextEdit.Wrap
                    Keys.onPressed: {
                        if (event.key === Qt.Key_Return && (event.modifiers & Qt.ControlModifier)) {
                            root.sendCurrentPrompt()
                            event.accepted = true
                        }
                    }
                }
                Column {
                    spacing: 6
                    Button { text: "Отправить"; onClicked: root.sendCurrentPrompt(); enabled: controller ? !controller.busy : true }
                    Button { text: "Отмена"; visible: controller ? controller.busy : false; onClicked: controller.cancelRequest() }
                }
            }
        }
    }

    AgentLogDrawer { id: logDrawer; anchors.right: parent.right; anchors.top: sceneBar.bottom; anchors.bottom: parent.bottom; width: Math.min(430, root.width * 0.42); controller: root.controller; opened: false; z: 20 }
    SettingsDialog { id: settings; anchors.fill: parent; controller: root.controller; visible: false; z: 30 }
}
