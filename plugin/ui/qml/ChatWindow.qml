import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Controls.Styles 1.4
import QtQuick.Layouts 1.1
import QtQuick.Window 2.2

Window {
    id: root
    objectName: "chatWindow"
    title: "STE AI • 3D/5D Инженерный ассистент"
    width: 1100
    height: 760
    minimumWidth: 860
    minimumHeight: 560
    color: "#f8fafc"
    flags: Qt.Window

    // Material 3 Color Palette
    readonly property color colPrimary: "#1976d2"
    readonly property color colPrimaryHover: "#1565c0"
    readonly property color colPrimaryPressed: "#0d47a1"
    readonly property color colPrimaryContainer: "#e8f0fe"
    readonly property color colOnPrimaryContainer: "#174ea6"
    readonly property color colBackground: "#f8fafc"
    readonly property color colSurface: "#ffffff"
    readonly property color colSurfaceVariant: "#f1f5f9"
    readonly property color colBorder: "#e2e8f0"
    readonly property color colBorderHover: "#cbd5e1"
    readonly property color colTextPrimary: "#1e293b"
    readonly property color colTextSecondary: "#64748b"
    readonly property color colTextTertiary: "#94a3b8"
    readonly property color colSuccess: "#10b981"
    readonly property color colSuccessContainer: "#ecfdf5"
    readonly property color colWarning: "#f59e0b"
    readonly property color colWarningContainer: "#fffbeb"
    readonly property color colError: "#ef4444"
    readonly property color colErrorContainer: "#fef2f2"

    // Safe accessor to context property 'controller'
    readonly property var activeCtrl: (typeof controller !== "undefined" && controller) ? controller : null
    readonly property var activeMgr: (typeof manager !== "undefined" && manager) ? manager : null

    function sendCurrentPrompt() {
        var ctrl = activeCtrl
        var textVal = promptInput.text ? promptInput.text.trim() : ""
        if (textVal.length === 0 || !ctrl) return
        ctrl.sendPrompt(textVal)
        promptInput.text = ""
    }

    Connections {
        target: activeCtrl
        onMessageAdded: {
            messageList.positionViewAtEnd()
        }
        onTaskStarted: {
            statusBadgeText.text = "Агент выполняет нарезку..."
            statusBadgeDot.color = root.colWarning
        }
        onTaskFinished: {
            statusBadgeText.text = (activeCtrl && activeCtrl.connected) ? "Слайсер подключён" : "Готов к работе"
            statusBadgeDot.color = root.colSuccess
        }
        onTaskFailed: {
            statusBadgeText.text = "Ошибка обработки"
            statusBadgeDot.color = root.colError
        }
        onConnectedChanged: {
            if (activeCtrl && activeCtrl.connected) {
                statusBadgeText.text = "Слайсер подключён"
                statusBadgeDot.color = root.colSuccess
            } else {
                statusBadgeText.text = "Офлайн"
                statusBadgeDot.color = root.colTextTertiary
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // =====================================================================
        // 1. MATERIAL APP BAR (HEADER)
        // =====================================================================
        Rectangle {
            id: header
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            color: root.colSurface
            border.color: root.colBorder
            border.width: 1
            z: 10

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 16
                spacing: 12

                // Logo Badge
                Rectangle {
                    width: 38
                    height: 38
                    radius: 10
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#2563eb" }
                        GradientStop { position: 1.0; color: "#1d4ed8" }
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "5D"
                        color: "#ffffff"
                        font.bold: true
                        font.pixelSize: 15
                    }
                }

                // Title & Subtitle
                Column {
                    spacing: 2
                    Row {
                        spacing: 6
                        Text {
                            text: "STE AI"
                            font.bold: true
                            font.pixelSize: 16
                            color: root.colTextPrimary
                        }
                        Text {
                            text: "•  3D/5D Инженерный ассистент"
                            font.pixelSize: 14
                            color: root.colTextSecondary
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                    Text {
                        text: "Stereotech Slicer  |  Автономная оптимизация и ReAct-нарезка"
                        font.pixelSize: 10
                        color: root.colTextTertiary
                    }
                }

                Item { Layout.fillWidth: true }

                // Live Status Badge
                Rectangle {
                    height: 30
                    radius: 15
                    color: root.colSurfaceVariant
                    border.color: root.colBorder
                    border.width: 1
                    implicitWidth: statusRow.width + 20

                    Row {
                        id: statusRow
                        anchors.centerIn: parent
                        spacing: 7
                        Rectangle {
                            id: statusBadgeDot
                            width: 8
                            height: 8
                            radius: 4
                            color: (activeCtrl && activeCtrl.connected) ? root.colSuccess : root.colWarning
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            id: statusBadgeText
                            text: (activeCtrl && activeCtrl.connected) ? "Слайсер подключён" : "Подключение к слайсеру..."
                            color: root.colTextSecondary
                            font.pixelSize: 11
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                // Settings Button
                Rectangle {
                    width: 108
                    height: 34
                    radius: 8
                    color: settingsBtnMouse.containsMouse ? root.colSurfaceVariant : "transparent"
                    border.color: settingsBtnMouse.containsMouse ? root.colBorderHover : root.colBorder
                    border.width: 1

                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Text { text: "⚙"; font.pixelSize: 14; color: root.colTextPrimary }
                        Text { text: "Настройки"; font.pixelSize: 12; font.weight: Font.Medium; color: root.colTextPrimary }
                    }

                    MouseArea {
                        id: settingsBtnMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (activeMgr && activeMgr.showSettingsDialog) {
                                activeMgr.showSettingsDialog()
                            } else if (activeCtrl && activeCtrl.openSettings) {
                                activeCtrl.openSettings()
                            }
                        }
                    }
                }

                // Log Drawer Button
                Rectangle {
                    width: 114
                    height: 34
                    radius: 8
                    color: logDrawer.opened ? root.colPrimary : (logBtnMouse.containsMouse ? root.colPrimaryContainer : root.colSurfaceVariant)
                    border.color: logDrawer.opened ? root.colPrimary : root.colBorder
                    border.width: 1

                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Text {
                            text: "📋"
                            font.pixelSize: 13
                            color: logDrawer.opened ? "#ffffff" : (logBtnMouse.containsMouse ? root.colPrimary : root.colTextSecondary)
                        }
                        Text {
                            text: "Лог агента"
                            font.pixelSize: 12
                            font.weight: Font.Medium
                            color: logDrawer.opened ? "#ffffff" : (logBtnMouse.containsMouse ? root.colPrimary : root.colTextPrimary)
                        }
                    }

                    MouseArea {
                        id: logBtnMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: logDrawer.opened = !logDrawer.opened
                    }
                }

                // =================================================================
                // PROMINENT CLOSE WINDOW BUTTON (User Requirement)
                // =================================================================
                Rectangle {
                    id: closeWindowBtn
                    width: 34
                    height: 34
                    radius: 17
                    color: closeWinMouse.containsMouse ? root.colErrorContainer : root.colSurfaceVariant
                    border.color: closeWinMouse.containsMouse ? "#fca5a5" : root.colBorder
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.pixelSize: 14
                        font.bold: true
                        color: closeWinMouse.containsMouse ? root.colError : root.colTextSecondary
                    }

                    MouseArea {
                        id: closeWinMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.close()
                    }
                }
            }
        }

        // =====================================================================
        // 2. SCENE CONTEXT BAR (Printer & Slicing Status)
        // =====================================================================
        Rectangle {
            id: sceneBar
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            color: root.colSurfaceVariant
            border.color: root.colBorder
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 20
                anchors.rightMargin: 16
                spacing: 16

                // Printer Chip
                Row {
                    spacing: 6
                    Text { text: "🖨"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: "Принтер: <b>" + (activeCtrl ? activeCtrl.printerName : "Stereotech Hybrid 530") + "</b>"
                        textFormat: Text.RichText
                        color: root.colTextPrimary
                        font.pixelSize: 11
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                // Mode Chip (Pill badge)
                Rectangle {
                    height: 24
                    radius: 6
                    color: (activeCtrl && activeCtrl.printMode === "5D") ? root.colPrimary : "#e2e8f0"
                    implicitWidth: modeRow.width + 14
                    Row {
                        id: modeRow
                        anchors.centerIn: parent
                        spacing: 4
                        Text {
                            text: "Режим: " + (activeCtrl ? activeCtrl.printMode : "3D")
                            font.bold: true
                            font.pixelSize: 10
                            color: (activeCtrl && activeCtrl.printMode === "5D") ? "#ffffff" : root.colTextPrimary
                        }
                    }
                }

                // Material Chip
                Row {
                    spacing: 6
                    Text { text: "🧶"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: "Материал: <b>" + (activeCtrl ? activeCtrl.material : "Не выбран") + "</b>"
                        textFormat: Text.RichText
                        color: root.colTextPrimary
                        font.pixelSize: 11
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                // Models Count
                Row {
                    spacing: 6
                    Text { text: "🧊"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: "Моделей на столе: <b>" + (activeCtrl ? activeCtrl.modelCount : 0) + "</b>"
                        textFormat: Text.RichText
                        color: root.colTextPrimary
                        font.pixelSize: 11
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                // Slicing result stats (if available)
                Row {
                    visible: activeCtrl ? (activeCtrl.printTime.length > 0) : false
                    spacing: 6
                    Text { text: "⏱"; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: "Время: <b>" + (activeCtrl ? activeCtrl.printTime : "") + "</b>"
                        textFormat: Text.RichText
                        color: "#047857"
                        font.pixelSize: 11
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }

                Item { Layout.fillWidth: true }

                // Clear Conversation Button
                Rectangle {
                    width: 104
                    height: 26
                    radius: 6
                    color: clearBtnMouse.containsMouse ? "#fee2e2" : "transparent"
                    border.color: clearBtnMouse.containsMouse ? "#fca5a5" : "transparent"
                    border.width: 1

                    Row {
                        anchors.centerIn: parent
                        spacing: 5
                        Text { text: "🗑"; font.pixelSize: 11 }
                        Text {
                            text: "Очистить чат"
                            font.pixelSize: 11
                            color: clearBtnMouse.containsMouse ? root.colError : root.colTextSecondary
                        }
                    }

                    MouseArea {
                        id: clearBtnMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (activeCtrl && !activeCtrl.busy) {
                                activeCtrl.clearConversation()
                            }
                        }
                    }
                }
            }
        }

        // =====================================================================
        // 3. CHAT MESSAGES LIST (FIXED ROBUST VERTICAL LAYOUT)
        // =====================================================================
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: messageList
                anchors.fill: parent
                anchors.margins: 16
                clip: true
                spacing: 12
                model: activeCtrl ? activeCtrl.messageModel : null

                delegate: Item {
                    id: msgDelegate
                    width: messageList.width
                    height: contentWrapper.height + 6

                    Item {
                        id: contentWrapper
                        width: parent.width
                        height: {
                            if (model.kind === "user") return userCard.height
                            if (model.kind === "tool_trace") return toolCard.height
                            if (model.kind === "system") return systemCard.height
                            return assistantCard.height
                        }

                        // -------------------------------------------------------------
                        // USER MESSAGE (Floats to Right)
                        // -------------------------------------------------------------
                        Rectangle {
                            id: userCard
                            visible: model.kind === "user"
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            width: Math.min(parent.width * 0.75, 680)
                            height: userCol.childrenRect.height + 20
                            radius: 12
                            color: root.colPrimaryContainer
                            border.color: "#bfdbfe"
                            border.width: 1

                            Column {
                                id: userCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 10
                                spacing: 4

                                RowLayout {
                                    width: parent.width
                                    spacing: 6
                                    Text { text: "👤"; font.pixelSize: 11 }
                                    Text { text: "Вы"; font.bold: true; font.pixelSize: 11; color: root.colOnPrimaryContainer }
                                    Item { Layout.fillWidth: true }
                                    Text { text: model.timestamp || ""; font.pixelSize: 10; color: root.colTextTertiary }
                                }

                                Text {
                                    width: parent.width
                                    text: model.text || ""
                                    wrapMode: Text.Wrap
                                    font.pixelSize: 13
                                    lineHeight: 1.25
                                    color: root.colOnPrimaryContainer
                                }
                            }
                        }

                        // -------------------------------------------------------------
                        // ASSISTANT MESSAGE (Floats to Left)
                        // -------------------------------------------------------------
                        Rectangle {
                            id: assistantCard
                            visible: model.kind === "assistant"
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            width: Math.min(parent.width * 0.82, 780)
                            height: assistantCol.childrenRect.height + 24
                            radius: 12
                            color: root.colSurface
                            border.color: root.colBorder
                            border.width: 1

                            Column {
                                id: assistantCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 12
                                spacing: 6

                                RowLayout {
                                    width: parent.width
                                    spacing: 6
                                    Rectangle {
                                        width: 20; height: 20; radius: 10
                                        color: "#2563eb"
                                        Text { anchors.centerIn: parent; text: "✦"; color: "#ffffff"; font.pixelSize: 10 }
                                    }
                                    Text { text: "STE AI Инженер"; font.bold: true; font.pixelSize: 12; color: root.colPrimary }
                                    Item { Layout.fillWidth: true }
                                    Text { text: model.timestamp || ""; font.pixelSize: 10; color: root.colTextTertiary }
                                }

                                Text {
                                    width: parent.width
                                    text: model.text || ""
                                    wrapMode: Text.Wrap
                                    font.pixelSize: 13
                                    lineHeight: 1.3
                                    color: root.colTextPrimary
                                }
                            }
                        }

                        // -------------------------------------------------------------
                        // TOOL TRACE (Compact, Expandable & Dismissible)
                        // -------------------------------------------------------------
                        Rectangle {
                            id: toolCard
                            visible: model.kind === "tool_trace"
                            property bool expanded: false
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            width: Math.min(parent.width * 0.88, 800)
                            height: toolCol.childrenRect.height + 16
                            radius: 8
                            color: model.status === "err" || model.status === "error" ? "#fef2f2" : "#f8fafc"
                            border.color: model.status === "err" || model.status === "error" ? "#fca5a5" : "#e2e8f0"
                            border.width: 1

                            Column {
                                id: toolCol
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 8
                                spacing: 6

                                // Header row (Always 1 clean compact line!)
                                RowLayout {
                                    width: parent.width
                                    spacing: 8

                                    Text { text: "⚡"; font.pixelSize: 12 }
                                    Text {
                                        text: model.text || model.toolName || "Вызов инструмента"
                                        font.bold: true
                                        font.pixelSize: 11
                                        color: "#0f172a"
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
                                        implicitWidth: toolBadgeText.width + 10

                                        Text {
                                            id: toolBadgeText
                                            anchors.centerIn: parent
                                            text: model.status === "ok" ? "✓ Успешно" : ((model.status === "err" || model.status === "error") ? "✕ Ошибка" : "⟳ В процессе")
                                            font.bold: true
                                            font.pixelSize: 9
                                            color: model.status === "ok" ? "#065f46" : ((model.status === "err" || model.status === "error") ? "#991b1b" : "#92400e")
                                        }
                                    }

                                    // Duration
                                    Text {
                                        visible: model.durationMs > 0
                                        text: model.durationMs + " ms"
                                        font.pixelSize: 10
                                        color: "#64748b"
                                    }

                                    // Toggle Expand Button (▼ / ▲)
                                    Rectangle {
                                        width: 22; height: 22; radius: 4
                                        color: toggleExpandMouse.containsMouse ? "#e2e8f0" : "transparent"
                                        Text {
                                            anchors.centerIn: parent
                                            text: toolCard.expanded ? "▲" : "▼"
                                            font.pixelSize: 9
                                            color: "#64748b"
                                        }
                                        MouseArea {
                                            id: toggleExpandMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: toolCard.expanded = !toolCard.expanded
                                        }
                                    }

                                    // Dismiss / Close Button (✕)
                                    Rectangle {
                                        width: 22; height: 22; radius: 11
                                        color: dismissToolMouse.containsMouse ? "#fee2e2" : "transparent"
                                        Text {
                                            anchors.centerIn: parent
                                            text: "✕"
                                            font.pixelSize: 10
                                            color: dismissToolMouse.containsMouse ? "#ef4444" : "#94a3b8"
                                        }
                                        MouseArea {
                                            id: dismissToolMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: toolCard.visible = false
                                        }
                                    }
                                }

                                // Expandable Details (ONLY when expanded = true!)
                                Rectangle {
                                    visible: toolCard.expanded && (model.toolArguments.length > 0 || model.toolResult.length > 0)
                                    width: parent.width
                                    height: Math.min(toolDetailsText.implicitHeight + 12, 160)
                                    radius: 6
                                    color: "#0f172a"
                                    clip: true

                                    Flickable {
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        contentWidth: toolDetailsText.width
                                        contentHeight: toolDetailsText.height
                                        clip: true

                                        Text {
                                            id: toolDetailsText
                                            text: (model.toolArguments.length > 0 ? "Параметры:\n" + model.toolArguments : "") +
                                                  (model.toolResult.length > 0 ? "\n\nРезультат:\n" + model.toolResult : "")
                                            color: "#38bdf8"
                                            font.family: "Consolas, 'Courier New', monospace"
                                            font.pixelSize: 10
                                            wrapMode: Text.Wrap
                                            width: toolCard.width - 30
                                        }
                                    }
                                }
                            }
                        }

                        // -------------------------------------------------------------
                        // SYSTEM MESSAGE (Compact Centered Pill)
                        // -------------------------------------------------------------
                        Rectangle {
                            id: systemCard
                            visible: model.kind === "system"
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: Math.min(systemText.implicitWidth + 24, parent.width * 0.9)
                            height: systemText.implicitHeight + 10
                            radius: 12
                            color: model.status === "error" ? "#fef2f2" : "#f1f5f9"
                            border.color: model.status === "error" ? "#fca5a5" : "#e2e8f0"
                            border.width: 1

                            Text {
                                id: systemText
                                anchors.centerIn: parent
                                text: model.text || ""
                                font.pixelSize: 11
                                color: model.status === "error" ? "#991b1b" : "#475569"
                                wrapMode: Text.Wrap
                                width: Math.min(implicitWidth, parent.width - 24)
                            }
                        }
                    }
                }

                // Welcome Empty State
                Item {
                    anchors.centerIn: parent
                    visible: messageList.count === 0
                    width: Math.min(parent.width * 0.8, 620)
                    height: emptyCol.height

                    Column {
                        id: emptyCol
                        width: parent.width
                        spacing: 12
                        anchors.horizontalCenter: parent.horizontalCenter

                        Rectangle {
                            width: 60
                            height: 60
                            radius: 30
                            color: root.colPrimaryContainer
                            anchors.horizontalCenter: parent.horizontalCenter
                            Text {
                                anchors.centerIn: parent
                                text: "✦"
                                font.pixelSize: 26
                                color: root.colPrimary
                            }
                        }

                        Text {
                            text: "Добро пожаловать в STE AI Ассистент!"
                            font.bold: true
                            font.pixelSize: 18
                            color: root.colTextPrimary
                            anchors.horizontalCenter: parent.horizontalCenter
                        }

                        Text {
                            text: "ИИ-инженер для автоматической подготовки и нарезки моделей под 3D и 5D печать."
                            font.pixelSize: 13
                            color: root.colTextSecondary
                            anchors.horizontalCenter: parent.horizontalCenter
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: root.colBorder
                        }

                        Grid {
                            columns: 2
                            spacing: 12
                            width: parent.width
                            anchors.horizontalCenter: parent.horizontalCenter

                            Rectangle {
                                width: (parent.width - 12) / 2
                                height: 58
                                radius: 8
                                color: root.colSurface
                                border.color: root.colBorder
                                border.width: 1
                                Row {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 8
                                    Text { text: "📎"; font.pixelSize: 18; anchors.verticalCenter: parent.verticalCenter }
                                    Column {
                                        anchors.verticalCenter: parent.verticalCenter
                                        Text { text: "1. Прикрепите модель"; font.bold: true; font.pixelSize: 11; color: root.colTextPrimary }
                                        Text { text: "STL, OBJ или 3MF деталь"; font.pixelSize: 10; color: root.colTextSecondary }
                                    }
                                }
                            }

                            Rectangle {
                                width: (parent.width - 12) / 2
                                height: 58
                                radius: 8
                                color: root.colSurface
                                border.color: root.colBorder
                                border.width: 1
                                Row {
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 8
                                    Text { text: "💬"; font.pixelSize: 18; anchors.verticalCenter: parent.verticalCenter }
                                    Column {
                                        anchors.verticalCenter: parent.verticalCenter
                                        Text { text: "2. Опишите задачу"; font.bold: true; font.pixelSize: 11; color: root.colTextPrimary }
                                        Text { text: "Материал, нагрузки, поддержки"; font.pixelSize: 10; color: root.colTextSecondary }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // =====================================================================
        // 4. QUICK PROMPT SUGGESTION CHIPS
        // =====================================================================
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 38
            color: root.colBackground

            Row {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 20
                spacing: 8

                Repeater {
                    model: [
                        { label: "🎯 Кронштейн под нагрузку", prompt: "Кронштейн под нагрузку, PETG, максимальная прочность" },
                        { label: "⚡ Без поддержек", prompt: "Ориентировать деталь для печати без поддержек" },
                        { label: "🔄 Подготовить 5D нарезку", prompt: "Выбрать режим 5D печати, рассчитать траектории и нарезать" },
                        { label: "📐 Анализ геометрии", prompt: "Проанализировать геометрию детали, габариты и нависания" }
                    ]
                    delegate: Rectangle {
                        height: 28
                        radius: 14
                        color: chipMouse.containsMouse ? root.colPrimaryContainer : root.colSurface
                        border.color: chipMouse.containsMouse ? "#bfdbfe" : root.colBorder
                        border.width: 1
                        implicitWidth: chipText.width + 20

                        Text {
                            id: chipText
                            anchors.centerIn: parent
                            text: modelData.label
                            font.pixelSize: 11
                            color: chipMouse.containsMouse ? root.colPrimary : root.colTextPrimary
                        }

                        MouseArea {
                            id: chipMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: promptInput.text = modelData.prompt
                        }
                    }
                }
            }
        }

        // =====================================================================
        // 5. ATTACHMENT BAR (DRAG & DROP + CHIPS)
        // =====================================================================
        AttachmentBar {
            id: attachments
            Layout.fillWidth: true
            controller: root.activeCtrl
            attachmentModel: activeCtrl ? activeCtrl.attachmentModel : null
        }

        // =====================================================================
        // 6. PROMPT INPUT BAR
        // =====================================================================
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 90
            Layout.margins: 16
            Layout.topMargin: 4
            color: root.colSurface
            border.color: promptInput.activeFocus ? root.colPrimary : root.colBorder
            border.width: promptInput.activeFocus ? 2 : 1
            radius: 12

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4

                // Busy progress indicator
                Rectangle {
                    visible: activeCtrl ? activeCtrl.busy : false
                    Layout.fillWidth: true
                    Layout.preferredHeight: 3
                    radius: 1.5
                    color: root.colPrimaryContainer
                    clip: true

                    Rectangle {
                        id: busyIndicatorBar
                        width: 120
                        height: parent.height
                        color: root.colPrimary
                        radius: 1.5

                        NumberAnimation on x {
                            running: activeCtrl ? activeCtrl.busy : false
                            from: -120
                            to: busyIndicatorBar.parent ? busyIndicatorBar.parent.width : 500
                            duration: 1200
                            loops: Animation.Infinite
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 10

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        TextArea {
                            id: promptInput
                            anchors.fill: parent
                            wrapMode: TextEdit.Wrap
                            font.pixelSize: 13
                            textColor: root.colTextPrimary
                            frameVisible: false

                            Keys.onPressed: {
                                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                                    if (event.modifiers & Qt.ShiftModifier) {
                                        // Shift+Enter inserts newline
                                        return
                                    }
                                    root.sendCurrentPrompt()
                                    event.accepted = true
                                }
                            }
                        }

                        Text {
                            anchors.fill: parent
                            anchors.margins: 4
                            text: "Опишите задачу печати (Enter для отправки, Shift+Enter для новой строки)…"
                            color: root.colTextTertiary
                            font.pixelSize: 13
                            visible: promptInput.text.length === 0 && !promptInput.activeFocus
                        }
                    }

                    // Action buttons
                    Column {
                        spacing: 6
                        Layout.alignment: Qt.AlignBottom

                        // Send Button
                        Rectangle {
                            width: 110
                            height: 38
                            radius: 8
                            color: {
                                if (activeCtrl && activeCtrl.busy) return "#94a3b8"
                                if (promptInput.text.trim().length === 0) return "#94a3b8"
                                return sendMouse.containsMouse ? root.colPrimaryHover : root.colPrimary
                            }

                            Row {
                                anchors.centerIn: parent
                                spacing: 6
                                Text {
                                    text: "Отправить"
                                    font.bold: true
                                    font.pixelSize: 12
                                    color: "#ffffff"
                                }
                                Text {
                                    text: "➔"
                                    font.bold: true
                                    font.pixelSize: 12
                                    color: "#ffffff"
                                }
                            }

                            MouseArea {
                                id: sendMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: (activeCtrl && activeCtrl.busy) ? Qt.ArrowCursor : Qt.PointingHandCursor
                                onClicked: root.sendCurrentPrompt()
                            }
                        }

                        // Cancel Button
                        Rectangle {
                            visible: activeCtrl ? activeCtrl.busy : false
                            width: 110
                            height: 28
                            radius: 6
                            color: cancelMouse.containsMouse ? "#fecaca" : root.colErrorContainer
                            border.color: "#fca5a5"
                            border.width: 1

                            Text {
                                anchors.centerIn: parent
                                text: "Отмена ✕"
                                font.bold: true
                                font.pixelSize: 11
                                color: root.colError
                            }

                            MouseArea {
                                id: cancelMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (activeCtrl && activeCtrl.cancelRequest) {
                                        activeCtrl.cancelRequest()
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // =========================================================================
    // 7. AGENT LOG DRAWER (Slide-in Panel with Prominent Close Button)
    // =========================================================================
    AgentLogDrawer {
        id: logDrawer
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 64
        anchors.bottom: parent.bottom
        width: Math.min(460, root.width * 0.44)
        controller: root.activeCtrl
        opened: false
        z: 30
    }
}
