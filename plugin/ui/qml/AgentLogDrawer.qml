import QtQuick 2.2
import QtQuick.Controls 1.4

Rectangle {
    id: root
    color: "#ffffff"
    border.color: "#cbdde6"
    property var controller
    property bool opened: false
    visible: opened

    Rectangle { anchors.fill: parent; color: "#ffffff"; opacity: 0.98 }
    Column {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 10
        Row {
            width: parent.width
            spacing: 8
            Label { text: "Действия агента"; color: "#263746"; font.pixelSize: 16; font.bold: true }
            Label { text: controller && controller.busy ? "● выполняется" : "● готов"; color: controller && controller.busy ? "#b2771f" : "#159a68"; font.pixelSize: 10; anchors.verticalCenter: parent.verticalCenter }
            Item { width: parent.width - 220; height: 1 }
            ToolButton { text: "×"; onClicked: root.opened = false }
        }
        Label { text: "Пользователь видит вызовы MCP-инструментов, их аргументы и результат."; color: "#758895"; font.pixelSize: 10; wrapMode: Text.Wrap; width: parent.width }
        ListView {
            id: logList
            width: parent.width
            height: parent.height - 75
            clip: true
            spacing: 7
            model: controller ? controller.toolLogModel : null
            delegate: Rectangle {
                width: logList.width - 6
                height: logColumn.height + 18
                radius: 6
                color: model.status === "err" ? "#fff3f3" : "#f7fbfd"
                border.color: model.status === "err" ? "#edc4c4" : "#d4e7ef"
                Column {
                    id: logColumn
                    anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 9; spacing: 4
                    Row {
                        width: parent.width
                        Label { text: model.label; color: "#29495d"; font.bold: true; font.pixelSize: 11; width: parent.width - 80; elide: Text.ElideRight }
                        Label { text: model.status === "ok" ? "OK" : (model.status === "err" ? "ERR" : "PENDING"); color: model.status === "ok" ? "#159a68" : (model.status === "err" ? "#c94b50" : "#b2771f"); font.bold: true; font.pixelSize: 9 }
                    }
                    Label { text: model.toolName; color: "#147db8"; font.family: "Monospace"; font.pixelSize: 9 }
                    Label { text: model.arguments; color: "#718593"; font.family: "Monospace"; font.pixelSize: 9; wrapMode: Text.Wrap; width: parent.width; maximumLineCount: 3; elide: Text.ElideRight; visible: model.arguments.length > 0 }
                    Label { text: (model.durationMs > 0 ? model.durationMs + " ms" : "") + (model.result.length > 0 ? " · " + model.result : ""); color: "#8b9aa5"; font.pixelSize: 9; wrapMode: Text.Wrap; width: parent.width; maximumLineCount: 2; elide: Text.ElideRight }
                }
            }
            Label { anchors.centerIn: parent; visible: logList.count === 0; text: "Вызовов инструментов пока нет"; color: "#9aabb5"; font.pixelSize: 11 }
        }
    }
}
