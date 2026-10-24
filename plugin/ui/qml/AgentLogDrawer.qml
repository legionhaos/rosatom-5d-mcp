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

    readonly property var activeCtrl: (typeof controller !== "undefined" && controller) ? controller : (typeof chatController !== "undefined" ? chatController : null)

    property string filterMode: "all" // "all", "ok", "err"

    function toolIcon(name) {
        if (!name) return "🛠";
        if (name.indexOf("geometry") !== -1) return "📐";
        if (name.indexOf("profile") !== -1 || name.indexOf("mode") !== -1) return "⚙";
        if (name.indexOf("transform") !== -1 || name.indexOf("scene") !== -1) return "🔄";
        if (name.indexOf("slicing") !== -1) return "✂";
        if (name.indexOf("export") !== -1) return "📦";
        return "🛠";
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        // Header Bar
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Rectangle {
                width: 32
                height: 32
                radius: 8
                color: "#eff6ff"
                Text {
                    anchors.centerIn: parent
                    text: "📋"
                    font.pixelSize: 16
                }
            }

            Column {
                Text {
                    text: "Журнал MCP-агента"
                    color: "#0f172a"
                    font.pixelSize: 15
                    font.bold: true
                }
                Text {
                    text: "Детальный аудит вызовов и ответов"
                    color: "#64748b"
                    font.pixelSize: 10
                }
            }

            Item { Layout.fillWidth: true }

            Rectangle {
                height: 28
                radius: 6
                color: copyLogMouse.containsMouse ? "#dbeafe" : "#eff6ff"
                border.color: "#bfdbfe"
                border.width: 1
                implicitWidth: copyLogText.width + 18
                Text { id: copyLogText; anchors.centerIn: parent; text: "Скопировать"; color: "#2563eb"; font.pixelSize: 10; font.bold: true }
                MouseArea { id: copyLogMouse; anchors.fill: parent; onClicked: { if (activeCtrl) activeCtrl.copyToolLog(); } }
            }

            // Close Button
            Rectangle {
                width: 28
                height: 28
                radius: 14
                color: closeDrawerMouse.containsMouse ? "#fee2e2" : "#f1f5f9"
                border.color: closeDrawerMouse.containsMouse ? "#fca5a5" : "#cbd5e1"
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: "✕"
                    font.pixelSize: 12
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

        // Filter Tabs
        Row {
            Layout.fillWidth: true
            spacing: 6

            Repeater {
                model: [
                    { id: "all", label: "Все вызовы" },
                    { id: "ok", label: "Успешные" },
                    { id: "err", label: "Ошибки" }
                ]

                delegate: Rectangle {
                    height: 26
                    radius: 13
                    implicitWidth: filterTabLabel.width + 18
                    color: root.filterMode === modelData.id ? "#2563eb" : "#f1f5f9"
                    border.color: root.filterMode === modelData.id ? "#2563eb" : "#e2e8f0"
                    border.width: 1

                    Text {
                        id: filterTabLabel
                        anchors.centerIn: parent
                        text: modelData.label
                        color: root.filterMode === modelData.id ? "#ffffff" : "#64748b"
                        font.pixelSize: 11
                        font.bold: root.filterMode === modelData.id
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.filterMode = modelData.id
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: "#e2e8f0"
        }

        // Tool Log List
        ListView {
            id: logList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 10
            model: activeCtrl ? activeCtrl.toolLogModel : null

            delegate: Rectangle {
                // Filter visibility
                readonly property bool matchesFilter: {
                    if (root.filterMode === "all") return true;
                    if (root.filterMode === "ok") return model.status === "ok";
                    if (root.filterMode === "err") return model.status === "err" || model.status === "error";
                    return true;
                }

                visible: matchesFilter
                width: logList.width - 4
                height: matchesFilter ? (logCardCol.height + 22) : 0
                radius: 8
                color: model.status === "err" || model.status === "error" ? "#fef2f2" : "#f8fafc"
                border.color: model.status === "err" || model.status === "error" ? "#fca5a5" : "#e2e8f0"
                border.width: 1

                Column {
                    id: logCardCol
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    spacing: 6

                    RowLayout {
                        width: parent.width
                        spacing: 8

                        Text {
                            text: root.toolIcon(model.toolName)
                            font.pixelSize: 13
                        }

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
                            implicitWidth: badgeText.width + 12

                            Text {
                                id: badgeText
                                anchors.centerIn: parent
                                text: model.status === "ok" ? "OK" : ((model.status === "err" || model.status === "error") ? "ОШИБКА" : "В ПРОЦЕССЕ")
                                font.bold: true
                                font.pixelSize: 9
                                color: model.status === "ok" ? "#065f46" : ((model.status === "err" || model.status === "error") ? "#991b1b" : "#92400e")
                            }
                        }
                    }

                    // Monospace Tool Call Signature
                    Rectangle {
                        width: parent.width
                        height: 20
                        radius: 4
                        color: "#f1f5f9"
                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                            text: "tool: " + model.toolName
                            color: "#2563eb"
                            font.family: "Consolas, 'Courier New', monospace"
                            font.pixelSize: 10
                        }
                    }

                    // Arguments
                    Text {
                        visible: model.arguments && model.arguments.length > 0 && model.arguments !== "{}"
                        text: "Параметры: " + model.arguments
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
                        spacing: 10
                        visible: model.durationMs > 0 || (model.result && model.result.length > 0)

                        Text {
                            visible: model.durationMs > 0
                            text: "⏱ " + model.durationMs + " ms"
                            color: "#64748b"
                            font.pixelSize: 10
                        }

                        Text {
                            visible: model.result && model.result.length > 0
                            text: "• " + model.result
                            color: "#334155"
                            font.pixelSize: 10
                            width: logCardCol.width - 100
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
                height: 120

                Column {
                    anchors.centerIn: parent
                    spacing: 8

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "📋"
                        font.pixelSize: 32
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "История вызовов пуста"
                        color: "#64748b"
                        font.pixelSize: 13
                        font.bold: true
                    }

                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Запустите анализ модели, чтобы увидеть шаги MCP"
                        color: "#94a3b8"
                        font.pixelSize: 11
                    }
                }
            }
        }
    }
}
