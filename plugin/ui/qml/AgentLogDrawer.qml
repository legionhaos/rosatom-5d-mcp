import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Layouts 1.1

Rectangle {
    id: root
    color: "#ffffff"
    border.color: "#cbd5e1"
    border.width: 1
    property var controller: (typeof chatController !== "undefined" && chatController) ? chatController : null
    property bool opened: false
    visible: opened

    // Safe accessor
    readonly property var activeCtrl: (typeof controller !== "undefined" && controller) ? controller : (typeof chatController !== "undefined" ? chatController : null)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        // Header with Title and Prominent Close Button
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                text: "Журнал MCP"
                color: "#1e293b"
                font.pixelSize: 16
                font.bold: true
            }

            Rectangle {
                height: 22
                radius: 11
                color: (activeCtrl && activeCtrl.busy) ? "#fffbeb" : "#ecfdf5"
                border.color: (activeCtrl && activeCtrl.busy) ? "#fde68a" : "#a7f3d0"
                border.width: 1
                implicitWidth: statusText.width + 14

                Row {
                    anchors.centerIn: parent
                    spacing: 4
                    Rectangle {
                        width: 6; height: 6; radius: 3
                        color: (activeCtrl && activeCtrl.busy) ? "#f59e0b" : "#10b981"
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        id: statusText
                        text: (activeCtrl && activeCtrl.busy) ? "выполняется" : "готов"
                        color: (activeCtrl && activeCtrl.busy) ? "#92400e" : "#065f46"
                        font.pixelSize: 10
                        font.bold: true
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // =================================================================
            // PROMINENT CLOSE BUTTON (✕) — ALWAYS VISIBLE & ACCESSIBLE
            // =================================================================
            Rectangle {
                width: 32
                height: 32
                radius: 16
                color: closeDrawerMouse.containsMouse ? "#fee2e2" : "#f1f5f9"
                border.color: closeDrawerMouse.containsMouse ? "#fca5a5" : "#cbd5e1"
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: "✕"
                    font.pixelSize: 14
                    font.bold: true
                    color: closeDrawerMouse.containsMouse ? "#ef4444" : "#64748b"
                }

                MouseArea {
                    id: closeDrawerMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.opened = false
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: "Детальный аудит вызовов MCP-инструментов, переданных параметров и полученных ответов."
            color: "#64748b"
            font.pixelSize: 11
            wrapMode: Text.Wrap
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: "#e2e8f0"
        }

        // List of tool calls
        ListView {
            id: logList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 10
            model: activeCtrl ? activeCtrl.toolLogModel : null

            delegate: Rectangle {
                width: logList.width - 6
                height: logCardCol.height + 18
                radius: 8
                color: model.status === "err" || model.status === "error" ? "#fef2f2" : "#f8fafc"
                border.color: model.status === "err" || model.status === "error" ? "#fca5a5" : "#e2e8f0"
                border.width: 1

                Column {
                    id: logCardCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 10
                    spacing: 5

                    RowLayout {
                        width: parent.width
                        spacing: 6

                        Text {
                            text: model.label || model.toolName
                            color: "#0f172a"
                            font.bold: true
                            font.pixelSize: 12
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        // Status Badge
                        Rectangle {
                            height: 20
                            radius: 4
                            color: model.status === "ok" ? "#ecfdf5" : ((model.status === "err" || model.status === "error") ? "#fee2e2" : "#fffbeb")
                            border.color: model.status === "ok" ? "#a7f3d0" : ((model.status === "err" || model.status === "error") ? "#fca5a5" : "#fde68a")
                            border.width: 1
                            implicitWidth: badgeText.width + 10

                            Text {
                                id: badgeText
                                anchors.centerIn: parent
                                text: model.status === "ok" ? "OK" : ((model.status === "err" || model.status === "error") ? "ERR" : "WAIT")
                                font.bold: true
                                font.pixelSize: 9
                                color: model.status === "ok" ? "#065f46" : ((model.status === "err" || model.status === "error") ? "#991b1b" : "#92400e")
                            }
                        }
                    }

                    // Monospace Tool Name
                    Text {
                        text: "tool: " + model.toolName
                        color: "#1976d2"
                        font.family: "Consolas, 'Courier New', monospace"
                        font.pixelSize: 10
                    }

                    // Arguments
                    Text {
                        visible: model.arguments && model.arguments.length > 0
                        text: model.arguments
                        color: "#475569"
                        font.family: "Consolas, 'Courier New', monospace"
                        font.pixelSize: 10
                        wrapMode: Text.Wrap
                        width: parent.width
                        maximumLineCount: 4
                        elide: Text.ElideRight
                    }

                    // Duration and Result
                    Row {
                        spacing: 8
                        visible: model.durationMs > 0 || (model.result && model.result.length > 0)

                        Text {
                            visible: model.durationMs > 0
                            text: "⏱ " + model.durationMs + " ms"
                            color: "#64748b"
                            font.pixelSize: 10
                        }

                        Text {
                            visible: model.result && model.result.length > 0
                            text: "•  " + model.result
                            color: "#64748b"
                            font.pixelSize: 10
                            width: logCardCol.width - 90
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            // Empty state
            Item {
                anchors.centerIn: parent
                visible: logList.count === 0
                width: parent.width - 40
                height: 100

                Column {
                    anchors.centerIn: parent
                    spacing: 8

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "📋"
                        font.pixelSize: 28
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Вызовов инструментов пока нет"
                        color: "#94a3b8"
                        font.pixelSize: 12
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Отправьте запрос, чтобы увидеть ReAct-шаги"
                        color: "#cbd5e1"
                        font.pixelSize: 11
                    }
                }
            }
        }
    }
}
