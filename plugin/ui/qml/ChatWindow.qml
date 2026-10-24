import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Dialogs 1.2
import QtQuick.Layouts 1.1
import QtQuick.Window 2.2

/*
 * STE Slicer · Premium AI 3D/5D Print Assistant
 * Complete modern UI/UX design with:
 *  - Interactive 3D Model Viewport & Multi-angle Camera Controls
 *  - Guided 5-stage Workflow Stepper
 *  - Rich Goal Selection & Smart Quick Prompts
 *  - Real-time ReAct MCP Execution Checklist & Telemetry
 *  - Intelligent Print Profile Dashboard & Engineering Reasoning
 *  - Interactive AI Co-pilot Chat for Instant Tweaks
 *  - 1-Click Hackathon Artifact Export (3MF + G-code + Screenshots)
 */
Window {
    id: root
    objectName: "chatWindow"
    title: "STE Slicer · AI 3D/5D Print Assistant"
    width: 1180
    height: 740
    minimumWidth: 1020
    minimumHeight: 640
    color: "#f8fafc"
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint

    // Design Tokens & Color Palette
    readonly property color ink: "#0f172a"
    readonly property color bodyText: "#334155"
    readonly property color muted: "#64748b"
    readonly property color subtle: "#94a3b8"
    readonly property color border: "#e2e8f0"
    readonly property color borderHover: "#cbd5e1"
    readonly property color cardBg: "#ffffff"
    readonly property color primary: "#2563eb"
    readonly property color primaryHover: "#1d4ed8"
    readonly property color primarySoft: "#eff6ff"
    readonly property color primaryBorder: "#bfdbfe"
    readonly property color success: "#10b981"
    readonly property color successSoft: "#ecfdf5"
    readonly property color successBorder: "#a7f3d0"
    readonly property color warning: "#f59e0b"
    readonly property color warningSoft: "#fffbeb"
    readonly property color danger: "#ef4444"
    readonly property color dangerSoft: "#fef2f2"
    readonly property color accent5D: "#7c3aed"
    readonly property color accent5DSoft: "#f5f3ff"

    readonly property var activeCtrl: (typeof controller !== "undefined" && controller) ? controller : (typeof chatController !== "undefined" ? chatController : null)
    readonly property var activeMgr: (typeof manager !== "undefined" && manager) ? manager : null

    // Workflow State: "upload", "analyze", "recommend", "apply", "done", "error"
    property string phase: "upload"
    property string lastError: ""
    property string analysisTitle: "Ожидаем запуск анализа"
    property string analysisDetail: "Проверим геометрию, нависания и доступные режимы печати."
    property int analysisIndex: 0
    property int applyIndex: 0

    property string selectedGoal: "Максимальная прочность"
    property var goals: [
        {
            title: "Максимальная прочность",
            icon: "🛡️",
            desc: "Ориентация вдоль слоёв нагрузки, повышенное заполнение, 5D траектории"
        },
        {
            title: "Быстрая печать",
            icon: "⚡",
            desc: "Оптимальная высота слоёв, минимум перемещений, без лишних поддержек"
        },
        {
            title: "Высокое качество",
            icon: "💎",
            desc: "Тонкие слои, деликатные переходы, минимальная шероховатость"
        },
        {
            title: "Минимум поддержек",
            icon: "🍃",
            desc: "Поворот детали для углов > 45°, чистые поверхности и экономия филамента"
        }
    ]

    property var quickPromptTags: [
        "Кронштейн под изгиб",
        "Шестерня / Втулка",
        "Корпус РЭА",
        "Режим 5D",
        "Материал PETG",
        "Углеволокно PA6-CF"
    ]

    property var analysisNames: [
        "Габариты, объем и масштаб детали",
        "Поиск нависающих элементов и критических углов",
        "Анализ возможности 5D-печати Stereotech",
        "Подбор материала, сопла и температур",
        "Расчёт прочности, заполнения и ориентации"
    ]

    property var applyNames: [
        "Режим кинематики (3D / 5D)",
        "Профиль материала и температуры",
        "Качество слоёв и сопло",
        "Ориентация и поворот модели на столе",
        "Поддержки и плотность заполнения"
    ]

    property int elapsedSec: 0
    property int finishedTools: 0
    property string activeToolName: ""

    property var toolTitles: {
        "analyze_mesh_geometry": "Анализ геометрии модели",
        "select_print_mode_and_profile": "Подбор режима и профиля",
        "modify_scene_and_parameters": "Изменение ориентации и параметров",
        "run_slicing_and_generate_gcode": "Слайсинг и расчёт G-code",
        "validate_and_export_artifacts": "Проверка и экспорт артефактов"
    }

    function fileCount() {
        return activeCtrl ? activeCtrl.modelCount : 0
    }

    function toolTitle(name) {
        return toolTitles[name] || name || "Шаг агента"
    }

    function elapsedText() {
        var m = Math.floor(elapsedSec / 60);
        var s = elapsedSec % 60;
        return m + ":" + (s < 10 ? "0" : "") + s;
    }

    function stepStatus(i, current) {
        if (i < current) return "done";
        if (i === current) return "active";
        return "wait";
    }

    function cancelTask() {
        if (activeCtrl) activeCtrl.cancelRequest();
        phase = phase === "apply" ? "recommend" : "upload";
    }

    onVisibleChanged: {
        if (visible && activeCtrl) activeCtrl.refreshPreview();
    }

    Timer {
        interval: 1000
        repeat: true
        running: (root.phase === "analyze" || root.phase === "apply") && activeCtrl && activeCtrl.busy
        onTriggered: root.elapsedSec += 1
    }

    function submitPrompt(text) {
        if (!activeCtrl || !text || text.trim().length === 0) return;
        activeCtrl.sendPrompt(text.trim());
    }

    function startAnalysis() {
        if (!activeCtrl || fileCount() === 0 || activeCtrl.busy) return;
        analysisIndex = 0;
        elapsedSec = 0;
        finishedTools = 0;
        changeMessages.clear();
        analysisTitle = "Инициализация ИИ-анализа";
        analysisDetail = "Передаём модель и задачу агенту…";
        phase = "analyze";

        var promptText = "Проанализируй прикреплённую модель для печати на Stereotech Hybrid 530. Цель: " +
            selectedGoal + ". " + customGoal.text +
            ". Определи оптимальный режим 3D/5D, материал, сопло, ориентацию, поддержки и подготовь инженерное обоснование. Пока не применяй изменения к сцене и не запускай слайсинг: используй геометрию и подбор профиля.";
        submitPrompt(promptText);
    }

    function askChange(text) {
        if (!activeCtrl || !text || text.trim().length === 0 || activeCtrl.busy) return;
        changeMessages.append({"role": "user", "text": text.trim()});
        changeInput.text = "";
        submitPrompt("Измени текущую рекомендацию по запросу пользователя: " + text.trim() + ". Верни обновлённые параметры и объясни последствия, но не применяй их пока.");
    }

    function applyRecommendation() {
        if (!activeCtrl || activeCtrl.busy) return;
        activeCtrl.applyRecommendation();
    }

    function startGcodeGeneration() {
        if (!activeCtrl || activeCtrl.busy) return;
        activeCtrl.generateGcode("model_submission");
    }

    function setAnalysisStep(toolName) {
        if (phase !== "analyze") return;
        activeToolName = toolName;
        analysisIndex = Math.min(4, analysisIndex + 1);
        analysisTitle = toolTitle(toolName);
        analysisDetail = "Выполняется инструмент " + toolName;
    }

    function finishPhase(text) {
        if (phase === "analyze") {
            analysisIndex = 5;
            if (text) changeMessages.append({"role": "assistant", "text": text});
            phase = "recommend";
        } else if (phase === "apply") {
            applyIndex = 5;
            phase = "done";
        } else if (phase === "recommend" && text) {
            changeMessages.append({"role": "assistant", "text": text});
        }
    }

    function setApplyStep(label) {
        if (phase !== "apply") return;
        applyIndex = Math.min(4, applyIndex + 1);
    }

    function resetToUpload() {
        if (activeCtrl && !activeCtrl.busy) activeCtrl.clearConversation();
        phase = "upload";
        lastError = "";
        analysisIndex = 0;
        applyIndex = 0;
    }

    FileDialog {
        id: modelDialog
        title: "Выберите 3D-модель (STL, OBJ, 3MF)"
        selectMultiple: true
        nameFilters: ["3D-модели (*.stl *.obj *.3mf)", "Все поддерживаемые файлы (*.stl *.obj *.3mf *.png *.jpg)"]
        onAccepted: {
            if (activeCtrl) {
                for (var i = 0; i < fileUrls.length; i++) activeCtrl.addAttachment(fileUrls[i].toString());
            }
        }
    }

    ListModel { id: changeMessages }

    Connections {
        target: activeCtrl

        onTaskStarted: {
            if (root.phase === "analyze") {
                root.analysisTitle = "Запущен анализ геометрии";
                root.analysisDetail = "Агент собирает данные о модели…";
            } else if (root.phase === "apply") {
                root.analysisTitle = "Применение профиля к STE Slicer";
            }
        }
        onToolStarted: {
            if (root.phase === "analyze") root.setAnalysisStep(arguments[0]);
            if (root.phase === "apply") root.setApplyStep(arguments[0]);
        }
        onToolFinished: {
            root.finishedTools += 1;
            if (root.phase === "analyze") root.analysisDetail = "Анализ данных инструмента завершён, агент выбирает следующий шаг…";
        }
        onResponseReady: root.finishPhase(arguments[0])
        onTaskFinished: {
            if (root.phase === "analyze" || root.phase === "apply") root.finishPhase("");
        }
        onTaskFailed: {
            root.lastError = arguments[0] || "Не удалось завершить операцию агента.";
            root.phase = "error";
        }
        onExportFinished: {
            var ok = arguments[0];
            var msg = arguments[1];
            if (ok) {
                exportNoticeBanner.visible = true;
                exportNoticeText.text = "✓ " + msg;
            }
        }
    }

    // =================================================================
    // 1. TOP HEADER & WORKFLOW STEPPER BAR
    // =================================================================
    Rectangle {
        id: header
        anchors.top: parent.top
        width: parent.width
        height: 66
        color: "#ffffff"
        border.color: root.border
        border.width: 1
        z: 10

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            anchors.rightMargin: 18
            spacing: 16

            // App Brand Logo
            Row {
                spacing: 10
                Rectangle {
                    width: 36
                    height: 36
                    radius: 8
                    color: "#2563eb"
                    Text {
                        anchors.centerIn: parent
                        text: "◈"
                        color: "#ffffff"
                        font.pixelSize: 20
                        font.bold: true
                    }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1
                    Text {
                        text: "STE AI Assistant"
                        color: root.ink
                        font.pixelSize: 15
                        font.bold: true
                    }
                    Text {
                        text: "3D / 5D stereotech print copilot"
                        color: root.muted
                        font.pixelSize: 10
                    }
                }
            }

            Item { width: 10; height: 1 }

            // Workflow Stage Stepper
            Row {
                spacing: 6
                anchors.verticalCenter: parent.verticalCenter

                Repeater {
                    model: [
                        { id: "upload", stepNum: "1", label: "Модель & Цель" },
                        { id: "analyze", stepNum: "2", label: "ИИ-Анализ" },
                        { id: "recommend", stepNum: "3", label: "Профиль & Чат" },
                        { id: "apply", stepNum: "4", label: "Применение" },
                        { id: "done", stepNum: "5", label: "Результат" }
                    ]

                    delegate: Row {
                        spacing: 6
                        anchors.verticalCenter: parent.verticalCenter

                        Rectangle {
                            height: 28
                            radius: 14
                            color: root.phase === modelData.id ? root.primarySoft : (
                                (modelData.id === "upload" && root.phase !== "upload") ||
                                (modelData.id === "analyze" && (root.phase === "recommend" || root.phase === "apply" || root.phase === "done")) ||
                                (modelData.id === "recommend" && (root.phase === "apply" || root.phase === "done")) ||
                                (modelData.id === "apply" && root.phase === "done") ? root.successSoft : "#f8fafc"
                            )
                            border.color: root.phase === modelData.id ? root.primary : (
                                (modelData.id === "upload" && root.phase !== "upload") ||
                                (modelData.id === "analyze" && (root.phase === "recommend" || root.phase === "apply" || root.phase === "done")) ||
                                (modelData.id === "recommend" && (root.phase === "apply" || root.phase === "done")) ||
                                (modelData.id === "apply" && root.phase === "done") ? root.successBorder : root.border
                            )
                            border.width: 1
                            implicitWidth: stepPillRow.width + 16

                            Row {
                                id: stepPillRow
                                anchors.centerIn: parent
                                spacing: 6

                                Text {
                                    text: (modelData.id === "upload" && root.phase !== "upload") ||
                                          (modelData.id === "analyze" && (root.phase === "recommend" || root.phase === "apply" || root.phase === "done")) ||
                                          (modelData.id === "recommend" && (root.phase === "apply" || root.phase === "done")) ||
                                          (modelData.id === "apply" && root.phase === "done") ? "✓" : modelData.stepNum
                                    color: root.phase === modelData.id ? root.primary : (
                                        (modelData.id === "upload" && root.phase !== "upload") ||
                                        (modelData.id === "analyze" && (root.phase === "recommend" || root.phase === "apply" || root.phase === "done")) ||
                                        (modelData.id === "recommend" && (root.phase === "apply" || root.phase === "done")) ||
                                        (modelData.id === "apply" && root.phase === "done") ? root.success : root.muted
                                    )
                                    font.pixelSize: 11
                                    font.bold: true
                                }

                                Text {
                                    text: modelData.label
                                    color: root.phase === modelData.id ? root.primary : root.ink
                                    font.pixelSize: 11
                                    font.bold: root.phase === modelData.id
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: (modelData.id === "upload" && root.phase !== "upload") || (modelData.id === "recommend" && root.phase === "done") ? Qt.PointingHandCursor : Qt.ArrowCursor
                                onClicked: {
                                    if (modelData.id === "upload" && !(activeCtrl && activeCtrl.busy)) {
                                        root.phase = "upload";
                                    } else if (modelData.id === "recommend" && root.phase === "done") {
                                        root.phase = "recommend";
                                    }
                                }
                            }
                        }

                        Text {
                            visible: index < 4
                            text: "›"
                            color: root.muted
                            font.pixelSize: 14
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // Slicer Status Indicator Pill
            Rectangle {
                height: 28
                radius: 14
                color: activeCtrl && activeCtrl.connected ? "#ecfdf5" : "#fffbeb"
                border.color: activeCtrl && activeCtrl.connected ? "#a7f3d0" : "#fde68a"
                border.width: 1
                implicitWidth: statusText.width + 26

                Row {
                    anchors.centerIn: parent
                    spacing: 6
                    Rectangle {
                        width: 7
                        height: 7
                        radius: 4
                        color: activeCtrl && activeCtrl.connected ? root.success : root.warning
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        id: statusText
                        text: activeCtrl && activeCtrl.connected ? "STE Slicer" : "Подключение…"
                        color: activeCtrl && activeCtrl.connected ? "#065f46" : "#92400e"
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
            }

            // MCP Log Drawer Toggle Button
            Rectangle {
                height: 32
                radius: 8
                color: logBtnMouse.containsMouse ? "#eff6ff" : "#f8fafc"
                border.color: logBtnMouse.containsMouse ? "#2563eb" : root.border
                border.width: 1
                implicitWidth: logBtnRow.width + 16

                Row {
                    id: logBtnRow
                    anchors.centerIn: parent
                    spacing: 6
                    Text { text: "📋"; font.pixelSize: 12 }
                    Text {
                        text: "Журнал MCP"
                        color: logBtnMouse.containsMouse ? root.primary : root.ink
                        font.pixelSize: 11
                        font.bold: true
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

            // Settings Button
            Rectangle {
                width: 32
                height: 32
                radius: 8
                color: settingsBtnMouse.containsMouse ? "#eff6ff" : "#f8fafc"
                border.color: settingsBtnMouse.containsMouse ? "#2563eb" : root.border
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: "⚙"
                    color: settingsBtnMouse.containsMouse ? root.primary : root.muted
                    font.pixelSize: 15
                }

                MouseArea {
                    id: settingsBtnMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { if (activeMgr) activeMgr.showSettingsDialog(); }
                }
            }

            // Close Window Button
            Rectangle {
                width: 30
                height: 30
                radius: 15
                color: closeBtnMouse.containsMouse ? "#fee2e2" : "#f8fafc"
                border.color: closeBtnMouse.containsMouse ? "#fca5a5" : root.border
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: "✕"
                    color: closeBtnMouse.containsMouse ? root.danger : root.muted
                    font.pixelSize: 12
                    font.bold: true
                }

                MouseArea {
                    id: closeBtnMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.close()
                }
            }
        }
    }

    // =================================================================
    // 2. CONTEXT SUB-BAR (PRINTER & SCENE TELEMETRY)
    // =================================================================
    Rectangle {
        id: contextBar
        anchors.top: header.bottom
        width: parent.width
        height: 38
        color: "#f1f5f9"
        border.color: root.border
        border.width: 1
        z: 9

        Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 24
            spacing: 24

            Row {
                spacing: 6
                anchors.verticalCenter: parent.verticalCenter
                Text { text: "🖨 Принтер:"; color: root.muted; font.pixelSize: 11 }
                Text { text: activeCtrl ? activeCtrl.printerName : "Stereotech Hybrid 530"; color: root.ink; font.pixelSize: 11; font.bold: true }
            }

            Row {
                spacing: 6
                anchors.verticalCenter: parent.verticalCenter
                Text { text: "⚡ Кинематика:"; color: root.muted; font.pixelSize: 11 }
                Text { text: (activeCtrl ? activeCtrl.printMode : "3D") + " (Stereotech 5-Axis ready)"; color: root.primary; font.pixelSize: 11; font.bold: true }
            }

            Row {
                spacing: 6
                anchors.verticalCenter: parent.verticalCenter
                Text { text: "🧵 Материал:"; color: root.muted; font.pixelSize: 11 }
                Text { text: activeCtrl ? activeCtrl.material : "Не выбран"; color: root.ink; font.pixelSize: 11; font.bold: true }
            }

            Row {
                spacing: 6
                anchors.verticalCenter: parent.verticalCenter
                Text { text: "🧊 Моделей на столе:"; color: root.muted; font.pixelSize: 11 }
                Text { text: "" + fileCount(); color: fileCount() > 0 ? root.success : root.muted; font.pixelSize: 11; font.bold: true }
            }
        }
    }

    // =================================================================
    // 3. MAIN WORKFLOW BODY CONTAINER
    // =================================================================
    Item {
        id: body
        anchors.top: contextBar.bottom
        anchors.bottom: parent.bottom
        width: parent.width

        // -------------------------------------------------------------
        // STAGE 1: UPLOAD & GOAL SELECTION
        // -------------------------------------------------------------
        Item {
            anchors.fill: parent
            visible: root.phase === "upload"

            Column {
                anchors.fill: parent
                anchors.margins: 24
                spacing: 12

                Text {
                    text: "Подготовка 3D-модели и цели печати"
                    color: root.ink
                    font.pixelSize: 22
                    font.bold: true
                }
                Text {
                    text: "Загрузите деталь, укажите ключевые критерии (прочность, скорость, поддержки) или опишите задачу своими словами. ИИ подберёт настройки без изменения исходного проекта.";
                    color: root.muted
                    font.pixelSize: 12
                }

                Row {
                    width: parent.width
                    height: parent.height - 120
                    spacing: 20

                    // LEFT: DRAG & DROP & SCENE CARD
                    Rectangle {
                        width: parent.width * 0.48
                        height: parent.height
                        radius: 12
                        color: dropArea.containsDrag ? "#eff6ff" : "#ffffff"
                        border.color: dropArea.containsDrag ? root.primary : root.border
                        border.width: dropArea.containsDrag ? 2 : 1

                        Column {
                            anchors.fill: parent
                            anchors.margins: 20
                            spacing: 14

                            // Drop Area Hero Box
                            Rectangle {
                                width: parent.width
                                height: fileCount() > 0 ? 150 : (parent.height - 140)
                                radius: 10
                                color: "#f8fafc"
                                border.color: dropArea.containsDrag ? root.primary : "#cbd5e1"
                                border.width: 1

                                Column {
                                    anchors.centerIn: parent
                                    spacing: 8

                                    Rectangle {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        width: 52
                                        height: 52
                                        radius: 26
                                        color: "#eff6ff"
                                        Text {
                                            anchors.centerIn: parent
                                            text: "⇧"
                                            color: root.primary
                                            font.pixelSize: 28
                                            font.bold: true
                                        }
                                    }

                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: "Перетащите 3D-модель сюда"
                                        color: root.ink
                                        font.pixelSize: 15
                                        font.bold: true
                                    }

                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: "STL · OBJ · 3MF · PNG / JPG (эскиз нагрузок)"
                                        color: root.muted
                                        font.pixelSize: 11
                                    }

                                    Rectangle {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        height: 32
                                        radius: 6
                                        color: selectFileBtnMouse.containsMouse ? "#1d4ed8" : "#2563eb"
                                        implicitWidth: selectFileText.width + 24

                                        Text {
                                            id: selectFileText
                                            anchors.centerIn: parent
                                            text: "Выбрать файл на диске…"
                                            color: "#ffffff"
                                            font.pixelSize: 11
                                            font.bold: true
                                        }

                                        MouseArea {
                                            id: selectFileBtnMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: modelDialog.open()
                                        }
                                    }
                                }

                                DropArea {
                                    id: dropArea
                                    anchors.fill: parent
                                    onDropped: {
                                        if (drop.hasUrls && activeCtrl) {
                                            for (var i = 0; i < drop.urls.length; i++) {
                                                activeCtrl.addAttachment(drop.urls[i].toString());
                                            }
                                        }
                                    }
                                }
                            }

                            // Scene Detected Notification Card (If models already in slicer)
                            Rectangle {
                                visible: fileCount() > 0
                                width: parent.width
                                height: 56
                                radius: 8
                                color: "#ecfdf5"
                                border.color: "#a7f3d0"
                                border.width: 1

                                Row {
                                    anchors.centerIn: parent
                                    spacing: 10
                                    Text { text: "✓"; color: root.success; font.pixelSize: 16; font.bold: true }
                                    Column {
                                        Text {
                                            text: "Модель готова к анализу: " + fileCount() + " шт."
                                            color: "#065f46"
                                            font.pixelSize: 12
                                            font.bold: true
                                        }
                                        Text {
                                            text: activeCtrl && activeCtrl.dimensionsText ? activeCtrl.dimensionsText : "Габариты детали прочитаны из STE Slicer"
                                            color: "#047857"
                                            font.pixelSize: 10
                                        }
                                    }
                                }
                            }

                            // Attached Files List Chips
                            AttachmentBar {
                                width: parent.width
                                controller: root.activeCtrl
                                attachmentModel: activeCtrl ? activeCtrl.attachmentModel : null
                            }
                        }
                    }

                    // RIGHT: GOAL SELECTION & PROMPT INPUT
                    Rectangle {
                        width: parent.width * 0.52 - 20
                        height: parent.height
                        radius: 12
                        color: "#ffffff"
                        border.color: root.border
                        border.width: 1

                        Column {
                            anchors.fill: parent
                            anchors.margins: 20
                            spacing: 12

                            Text {
                                text: "1. Выберите цель печати"
                                color: root.ink
                                font.pixelSize: 14
                                font.bold: true
                            }

                            // 4 Goal Cards Grid
                            Grid {
                                columns: 2
                                spacing: 10
                                width: parent.width

                                Repeater {
                                    model: root.goals
                                    delegate: Rectangle {
                                        width: (parent.width - 10) / 2
                                        height: 72
                                        radius: 8
                                        color: root.selectedGoal === modelData.title ? root.primarySoft : "#f8fafc"
                                        border.color: root.selectedGoal === modelData.title ? root.primary : root.border
                                        border.width: root.selectedGoal === modelData.title ? 1.5 : 1

                                        Column {
                                            anchors.fill: parent
                                            anchors.margins: 10
                                            spacing: 3

                                            Row {
                                                spacing: 6
                                                Text { text: modelData.icon; font.pixelSize: 13 }
                                                Text {
                                                    text: modelData.title
                                                    color: root.selectedGoal === modelData.title ? root.primary : root.ink
                                                    font.pixelSize: 11
                                                    font.bold: true
                                                }
                                            }

                                            Text {
                                                text: modelData.desc
                                                color: root.muted
                                                font.pixelSize: 9
                                                width: parent.width
                                                wrapMode: Text.Wrap
                                                maximumLineCount: 2
                                                elide: Text.ElideRight
                                            }
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.selectedGoal = modelData.title
                                        }
                                    }
                                }
                            }

                            Text {
                                text: "2. Дополнительные требования и пожелания (ИИ-промпт)"
                                color: root.ink
                                font.pixelSize: 13
                                font.bold: true
                            }

                            // Quick Prompt Suggestion Tags Flow
                            Flow {
                                width: parent.width
                                spacing: 6

                                Repeater {
                                    model: root.quickPromptTags
                                    delegate: Rectangle {
                                        height: 24
                                        radius: 12
                                        color: tagMouse.containsMouse ? "#eff6ff" : "#f1f5f9"
                                        border.color: tagMouse.containsMouse ? "#2563eb" : "#e2e8f0"
                                        border.width: 1
                                        implicitWidth: tagLabel.width + 16

                                        Text {
                                            id: tagLabel
                                            anchors.centerIn: parent
                                            text: "+ " + modelData
                                            color: tagMouse.containsMouse ? root.primary : "#475569"
                                            font.pixelSize: 10
                                        }

                                        MouseArea {
                                            id: tagMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                if (customGoal.text.length > 0) {
                                                    customGoal.text += ", " + modelData;
                                                } else {
                                                    customGoal.text = modelData;
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            // Custom Prompt Text Area
                            Rectangle {
                                width: parent.width
                                height: 86
                                radius: 8
                                color: "#f8fafc"
                                border.color: customGoal.activeFocus ? root.primary : root.border
                                border.width: 1

                                TextArea {
                                    id: customGoal
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    frameVisible: false
                                    wrapMode: TextEdit.Wrap
                                    font.pixelSize: 11
                                    textColor: root.ink
                                }

                                Text {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.margins: 12
                                    visible: customGoal.text.length === 0 && !customGoal.activeFocus
                                    text: "Например: кронштейн под вертикальную нагрузку 50 кг, материал PETG или PA6-CF, без поддержек в отверстиях..."
                                    color: root.subtle
                                    font.pixelSize: 11
                                    wrapMode: Text.Wrap
                                    width: parent.width - 24
                                }
                            }
                        }
                    }
                }
            }

            // Bottom Action Bar
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 60
                color: "#ffffff"
                border.color: root.border
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 24
                    anchors.rightMargin: 24

                    Row {
                        spacing: 8
                        Text { text: "💡"; font.pixelSize: 13 }
                        Text {
                            text: "ИИ подберёт кинематику 3D/5D, материал и ориентацию без изменения текущего проекта"
                            color: root.muted
                            font.pixelSize: 11
                        }
                    }

                    Item { Layout.fillWidth: true }

                    Rectangle {
                        height: 38
                        radius: 8
                        color: (fileCount() > 0 && !(activeCtrl && activeCtrl.busy)) ? (startBtnMouse.containsMouse ? "#1d4ed8" : "#2563eb") : "#cbd5e1"
                        implicitWidth: startBtnText.width + 30

                        Row {
                            id: startBtnText
                            anchors.centerIn: parent
                            spacing: 8
                            Text {
                                text: "Начать ИИ-анализ модели"
                                color: "#ffffff"
                                font.pixelSize: 12
                                font.bold: true
                            }
                            Text { text: "→"; color: "#ffffff"; font.pixelSize: 14; font.bold: true }
                        }

                        MouseArea {
                            id: startBtnMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: (fileCount() > 0 && !(activeCtrl && activeCtrl.busy)) ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.startAnalysis()
                        }
                    }
                }
            }
        }

        // -------------------------------------------------------------
        // STAGE 2: AI ANALYSIS & REACT TELEMETRY
        // -------------------------------------------------------------
        Item {
            anchors.fill: parent
            anchors.margins: 24
            visible: root.phase === "analyze"

            Column {
                anchors.fill: parent
                spacing: 16

                Text {
                    text: "ИИ-анализ модели и подбор профиля печати"
                    color: root.ink
                    font.pixelSize: 22
                    font.bold: true
                }
                Text {
                    text: "Агент проверяет геометрию, критические углы нависания и ограничения кинематики перед формированием рекомендаций.";
                    color: root.muted
                    font.pixelSize: 12
                }

                Row {
                    width: parent.width
                    height: parent.height - 90
                    spacing: 20

                    // LEFT: LIVE 3D MODEL PREVIEW
                    Rectangle {
                        width: parent.width * 0.44
                        height: parent.height
                        radius: 12
                        color: "#ffffff"
                        border.color: root.border
                        border.width: 1

                        Column {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8

                            Text {
                                text: "3D-ПРЕДПРОСМОТР МОДЕЛИ В РЕАЛЬНОМ ВРЕМЕНИ"
                                color: root.muted
                                font.pixelSize: 10
                                font.bold: true
                            }

                            ModelPreview {
                                width: parent.width
                                height: parent.height - 65
                                controller: root.activeCtrl
                            }

                            Text {
                                text: activeCtrl && activeCtrl.modelInfo ? activeCtrl.modelInfo : "Определение габаритов детали…"
                                color: root.bodyText
                                font.pixelSize: 11
                                font.bold: true
                                horizontalAlignment: Text.AlignHCenter
                                width: parent.width
                                elide: Text.ElideRight
                            }
                        }
                    }

                    // RIGHT: AGENT REACT EXECUTION CARD
                    Rectangle {
                        width: parent.width * 0.56 - 20
                        height: parent.height
                        radius: 12
                        color: "#ffffff"
                        border.color: root.border
                        border.width: 1

                        Column {
                            anchors.fill: parent
                            anchors.margins: 22
                            spacing: 14

                            // Top Progress Card Header
                            RowLayout {
                                width: parent.width
                                spacing: 10

                                StepIcon {
                                    status: activeCtrl && activeCtrl.busy ? "active" : "done"
                                    activeColor: root.primary
                                    doneColor: root.success
                                }

                                Text {
                                    text: root.analysisTitle
                                    color: root.ink
                                    font.pixelSize: 15
                                    font.bold: true
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }

                                Text {
                                    text: Math.min(100, Math.max(15, root.analysisIndex * 20)) + "%"
                                    color: root.primary
                                    font.pixelSize: 13
                                    font.bold: true
                                }
                            }

                            // Subtitle & Timer
                            Text {
                                text: root.analysisDetail + " · Прошло времени: " + root.elapsedText()
                                color: root.muted
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                                width: parent.width
                            }

                            // Animated Progress Track
                            ProgressTrack {
                                width: parent.width
                                value: Math.max(0.15, root.analysisIndex / 5.0)
                                busy: activeCtrl && activeCtrl.busy
                                barColor: root.primary
                            }

                            // ReAct Checklist
                            Column {
                                width: parent.width
                                spacing: 2

                                Repeater {
                                    model: root.analysisNames
                                    delegate: StepRow {
                                        width: parent.width
                                        label: modelData
                                        status: root.stepStatus(index, root.analysisIndex)
                                        inkColor: root.ink
                                        mutedColor: root.muted
                                        primaryColor: root.primary
                                        successColor: root.success
                                    }
                                }
                            }

                            // Active Tool Monospace Card
                            Rectangle {
                                width: parent.width
                                height: 42
                                radius: 8
                                color: "#f8fafc"
                                border.color: "#e2e8f0"
                                border.width: 1

                                Row {
                                    anchors.centerIn: parent
                                    spacing: 8
                                    Text { text: "⚡ MCP:"; color: root.primary; font.pixelSize: 11; font.bold: true }
                                    Text {
                                        text: root.activeToolName ? root.activeToolName : "Инициализация агента и сбор контекста"
                                        color: "#334155"
                                        font.family: "Consolas, 'Courier New', monospace"
                                        font.pixelSize: 10
                                    }
                                }
                            }

                            Item { Layout.fillHeight: true }

                            // Slow LLM Hint
                            Text {
                                width: parent.width
                                visible: root.elapsedSec >= 40 && activeCtrl && activeCtrl.busy
                                text: "💡 Ответ занимает больше обычного. Шаги ReAct выполняются через LLM API, на медленном провайдере это может занять 1–2 минуты."
                                color: root.warning
                                font.pixelSize: 10
                                wrapMode: Text.Wrap
                            }

                            // Cancel Button
                            Rectangle {
                                height: 32
                                radius: 6
                                color: cancelBtnMouse.containsMouse ? "#fee2e2" : "#f1f5f9"
                                border.color: cancelBtnMouse.containsMouse ? "#fca5a5" : "#cbd5e1"
                                border.width: 1
                                implicitWidth: cancelBtnText.width + 24
                                visible: activeCtrl && activeCtrl.busy

                                Text {
                                    id: cancelBtnText
                                    anchors.centerIn: parent
                                    text: "Отменить анализ"
                                    color: cancelBtnMouse.containsMouse ? root.danger : root.muted
                                    font.pixelSize: 11
                                    font.bold: true
                                }

                                MouseArea {
                                    id: cancelBtnMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: root.cancelTask()
                                }
                            }
                        }
                    }
                }
            }
        }

        // -------------------------------------------------------------
        // STAGE 3: RECOMMENDATION DASHBOARD & INTERACTIVE AI CHAT
        // -------------------------------------------------------------
        Item {
            anchors.fill: parent
            anchors.margins: 20
            visible: root.phase === "recommend"

            Column {
                anchors.fill: parent
                spacing: 10

                // Recommendation Header
                RowLayout {
                    width: parent.width

                    Column {
                        Text {
                            text: "Рекомендованный профиль печати готов"
                            color: root.ink
                            font.pixelSize: 22
                            font.bold: true
                        }
                        Text {
                            text: "Проверьте параметры. Вы можете попросить ИИ скорректировать их перед применением к слайсеру.";
                            color: root.muted
                            font.pixelSize: 11
                        }
                    }

                    Item { Layout.fillWidth: true }

                    Rectangle {
                        height: 28
                        radius: 14
                        color: "#ecfdf5"
                        border.color: "#a7f3d0"
                        border.width: 1
                        implicitWidth: readyBadgeText.width + 20

                        Row {
                            id: readyBadgeText
                            anchors.centerIn: parent
                            spacing: 6
                            Text { text: "✓"; color: root.success; font.pixelSize: 12; font.bold: true }
                            Text { text: "Готово к применению"; color: "#065f46"; font.pixelSize: 11; font.bold: true }
                        }
                    }
                }

                // 3-Column Layout: Model (28%), Profile Specs (38%), AI Chat (34%)
                Row {
                    width: parent.width
                    height: parent.height - 110
                    spacing: 12

                    // COL 1: 3D MODEL VIEWPORT
                    Rectangle {
                        width: parent.width * 0.28
                        height: parent.height
                        radius: 10
                        color: "#ffffff"
                        border.color: root.border
                        border.width: 1

                        Column {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 6

                            Text {
                                text: "ОРИЕНТАЦИЯ МОДЕЛИ"
                                color: root.muted
                                font.pixelSize: 9
                                font.bold: true
                            }

                            ModelPreview {
                                width: parent.width
                                height: parent.height - 75
                                controller: root.activeCtrl
                            }

                            Rectangle {
                                width: parent.width
                                height: 32
                                radius: 6
                                color: "#eff6ff"
                                border.color: "#bfdbfe"
                                border.width: 1

                                Row {
                                    anchors.centerIn: parent
                                    spacing: 6
                                    Text { text: "✦"; color: root.primary; font.pixelSize: 11 }
                                    Text {
                                        text: activeCtrl && activeCtrl.rotationText ? activeCtrl.rotationText : "Ориентация оптимизирована"
                                        color: root.primary
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                }
                            }
                        }
                    }

                    // COL 2: CALCULATED PROFILE SPECS & REASONING
                    Rectangle {
                        width: parent.width * 0.38
                        height: parent.height
                        radius: 10
                        color: "#ffffff"
                        border.color: root.border
                        border.width: 1

                        Column {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 8

                            Text {
                                text: "Подобранные характеристики печати"
                                color: root.ink
                                font.pixelSize: 13
                                font.bold: true
                            }

                            // Mode & Material Pill Badges
                            Row {
                                spacing: 8

                                Rectangle {
                                    height: 24
                                    radius: 12
                                    color: activeCtrl && activeCtrl.printMode === "5D" ? "#581c87" : "#1e3a8a"
                                    implicitWidth: modePillText.width + 16
                                    Text {
                                        id: modePillText
                                        anchors.centerIn: parent
                                        text: (activeCtrl && activeCtrl.printMode === "5D" ? "⚡ 5D Режим" : "🧊 3D Режим")
                                        color: "#ffffff"
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                }

                                Rectangle {
                                    height: 24
                                    radius: 12
                                    color: "#f1f5f9"
                                    border.color: "#cbd5e1"
                                    border.width: 1
                                    implicitWidth: matPillText.width + 16
                                    Text {
                                        id: matPillText
                                        anchors.centerIn: parent
                                        text: "🧵 " + (activeCtrl ? activeCtrl.material : "PA6-CF")
                                        color: "#1e293b"
                                        font.pixelSize: 10
                                        font.bold: true
                                    }
                                }
                            }

                            // Parameters Grid / List
                            Column {
                                width: parent.width

                                Repeater {
                                    model: [
                                        ["Профиль качества", activeCtrl ? activeCtrl.profileName : "5D Structural"],
                                        ["Высота слоя", activeCtrl ? activeCtrl.layerHeight : "0.20 мм"],
                                        ["Сопло", "0.4 мм · закалённое"],
                                        ["Заполнение детали", (activeCtrl ? activeCtrl.infillDensity : "50%") + " (" + (activeCtrl ? activeCtrl.infillPattern : "Gyroid") + ")"],
                                        ["Стенки", activeCtrl ? activeCtrl.wallLineCount : "4 линии"],
                                        ["Температура сопла / стола", (activeCtrl ? activeCtrl.printTemperature : "275 °C") + " / " + (activeCtrl ? activeCtrl.bedTemperature : "90 °C")],
                                        ["Поддержки детали", activeCtrl ? activeCtrl.supportText : "Отключены (5D)"],
                                        ["Расчётное время", activeCtrl && activeCtrl.printTime ? activeCtrl.printTime : "~ 1 ч 15 мин"],
                                        ["Расход материала", activeCtrl && activeCtrl.materialUsage ? activeCtrl.materialUsage : "~ 48.5 г"]
                                    ]

                                    delegate: Rectangle {
                                        width: parent.width
                                        height: 25
                                        color: index % 2 === 0 ? "#f8fafc" : "#ffffff"

                                        Text {
                                            anchors.left: parent.left
                                            anchors.leftMargin: 8
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: modelData[0]
                                            color: root.muted
                                            font.pixelSize: 10
                                        }

                                        Text {
                                            anchors.right: parent.right
                                            anchors.rightMargin: 8
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: modelData[1]
                                            color: index === 0 || index === 1 || index === 3 ? root.primary : root.ink
                                            font.pixelSize: 10
                                            font.bold: index === 0 || index === 1
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                width: parent.width
                                height: 1
                                color: root.border
                            }

                        }
                    }

                    // COL 3: INTERACTIVE AI CO-PILOT CHAT
                    Rectangle {
                        width: parent.width * 0.72 - 24
                        height: parent.height
                        radius: 10
                        color: "#ffffff"
                        border.color: root.border
                        border.width: 1

                        Column {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8

                            Row {
                                spacing: 6
                                Text { text: "✦"; color: root.primary; font.pixelSize: 14 }
                                Column {
                                    Text { text: "Диалог с ИИ-ассистентом"; color: root.ink; font.pixelSize: 12; font.bold: true }
                                    Text { text: "Задайте вопрос или измените параметр"; color: root.muted; font.pixelSize: 9 }
                                }
                            }

                            // Quick Tweak Chips
                            Flow {
                                width: parent.width
                                spacing: 4

                                Repeater {
                                    model: ["Почему так?", "Быстрее", "Без поддержек", "Включить 5D", "Сменить на PETG"]
                                    delegate: Rectangle {
                                        height: 22
                                        radius: 11
                                        color: chipMouse.containsMouse ? "#dbeafe" : "#f1f5f9"
                                        border.color: chipMouse.containsMouse ? "#2563eb" : "#e2e8f0"
                                        border.width: 1
                                        implicitWidth: chipLabel.width + 14

                                        Text {
                                            id: chipLabel
                                            anchors.centerIn: parent
                                            text: modelData
                                            font.pixelSize: 9
                                            color: "#1e293b"
                                        }

                                        MouseArea {
                                            id: chipMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: root.askChange(modelData)
                                        }
                                    }
                                }
                            }

                            // Chat Messages List
                            ListView {
                                id: changeList
                                width: parent.width
                                height: parent.height - 145
                                clip: true
                                spacing: 6
                                model: changeMessages
                                onCountChanged: positionViewAtEnd()

                                delegate: Rectangle {
                                    width: changeList.width
                                    height: msgText.implicitHeight + 16
                                    radius: 8
                                    color: model.role === "user" ? root.primarySoft : "#f8fafc"
                                    border.color: model.role === "user" ? root.primaryBorder : root.border
                                    border.width: 1

                                    Text {
                                        id: msgText
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        text: model.text
                                        textFormat: Text.RichText
                                        color: root.ink
                                        font.pixelSize: 10
                                        wrapMode: Text.Wrap
                                    }
                                }
                            }

                            // Input Row
                            Row {
                                width: parent.width
                                spacing: 6

                                TextField {
                                    id: changeInput
                                    width: parent.width - 44
                                    height: 32
                                    placeholderText: "Например: поставь заполнение 70%"
                                    font.pixelSize: 10
                                    onAccepted: root.askChange(text)
                                }

                                Rectangle {
                                    width: 38
                                    height: 32
                                    radius: 6
                                    color: (!(activeCtrl && activeCtrl.busy) && changeInput.text.trim().length > 0) ? (sendBtnMouse.containsMouse ? "#1d4ed8" : "#2563eb") : "#cbd5e1"

                                    Text {
                                        anchors.centerIn: parent
                                        text: "↑"
                                        color: "#ffffff"
                                        font.pixelSize: 14
                                        font.bold: true
                                    }

                                    MouseArea {
                                        id: sendBtnMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: root.askChange(changeInput.text)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Bottom Action Bar
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 58
                color: "#ffffff"
                border.color: root.border
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 24
                    anchors.rightMargin: 24

                    Rectangle {
                        height: 36
                        radius: 6
                        color: backBtnMouse.containsMouse ? "#e2e8f0" : "#f1f5f9"
                        border.color: "#cbd5e1"
                        border.width: 1
                        implicitWidth: backBtnText.width + 24

                        Text {
                            id: backBtnText
                            anchors.centerIn: parent
                            text: "← Изменить задачу"
                            color: root.bodyText
                            font.pixelSize: 11
                            font.bold: true
                        }

                        MouseArea {
                            id: backBtnMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.resetToUpload()
                        }
                    }

                    Item { Layout.fillWidth: true }

                    Rectangle {
                        height: 38
                        radius: 8
                        color: !(activeCtrl && activeCtrl.busy) ? (applyBtnMouse.containsMouse ? "#1d4ed8" : "#2563eb") : "#cbd5e1"
                        implicitWidth: applyBtnText.width + 30

                        Row {
                            id: applyBtnText
                            anchors.centerIn: parent
                            spacing: 8
                            Text {
                                text: "Применить настройки в слайсере"
                                color: "#ffffff"
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }

                        MouseArea {
                            id: applyBtnMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: !(activeCtrl && activeCtrl.busy) ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.applyRecommendation()
                        }
                    }

                    Rectangle {
                        height: 38
                        radius: 8
                        color: !(activeCtrl && activeCtrl.busy) ? (sliceBtnMouse.containsMouse ? "#047857" : "#059669") : "#cbd5e1"
                        implicitWidth: sliceBtnText.width + 30

                        Text {
                            id: sliceBtnText
                            anchors.centerIn: parent
                            text: "Создать G-code"
                            color: "#ffffff"
                            font.pixelSize: 12
                            font.bold: true
                        }
                        MouseArea {
                            id: sliceBtnMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: !(activeCtrl && activeCtrl.busy) ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: { if (activeCtrl) activeCtrl.generateGcode("model_submission"); }
                        }
                    }
                }
            }
        }

        // -------------------------------------------------------------
        // STAGE 4: APPLYING SETTINGS
        // -------------------------------------------------------------
        Item {
            anchors.fill: parent
            anchors.margins: 30
            visible: root.phase === "apply"

            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 80, 720)
                spacing: 16

                Text {
                    text: "Применение профиля к STE Slicer"
                    color: root.ink
                    font.pixelSize: 24
                    font.bold: true
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Text {
                    text: "Передаём выбранный профиль, ориентацию и параметры кинематики в главный поток слайсера.";
                    color: root.muted
                    font.pixelSize: 12
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Rectangle {
                    width: parent.width
                    height: applyCardCol.implicitHeight + 48
                    radius: 12
                    color: "#ffffff"
                    border.color: root.border
                    border.width: 1

                    Column {
                        id: applyCardCol
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 24
                        spacing: 10

                        RowLayout {
                            width: parent.width
                            StepIcon {
                                status: activeCtrl && activeCtrl.busy ? "active" : "done"
                                activeColor: root.primary
                                doneColor: root.success
                            }
                            Text {
                                text: "Настройка параметров сцены"
                                color: root.ink
                                font.bold: true
                                font.pixelSize: 14
                                Layout.fillWidth: true
                            }
                            Text {
                                text: Math.min(100, root.applyIndex * 20) + "%"
                                color: root.primary
                                font.bold: true
                                font.pixelSize: 13
                            }
                        }

                        ProgressTrack {
                            width: parent.width
                            value: root.applyIndex / 5.0
                            busy: activeCtrl && activeCtrl.busy
                            barColor: root.primary
                        }

                        Repeater {
                            model: root.applyNames
                            delegate: StepRow {
                                width: parent.width
                                label: modelData
                                status: root.stepStatus(index, root.applyIndex)
                                inkColor: root.ink
                                mutedColor: root.muted
                                primaryColor: root.primary
                                successColor: root.success
                            }
                        }
                    }
                }

                Text {
                    text: "Прошло: " + root.elapsedText()
                    color: root.muted
                    font.pixelSize: 11
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: 32
                    radius: 6
                    color: cancelApplyMouse.containsMouse ? "#fee2e2" : "#f1f5f9"
                    border.color: "#cbd5e1"
                    border.width: 1
                    implicitWidth: cancelApplyText.width + 24

                    Text {
                        id: cancelApplyText
                        anchors.centerIn: parent
                        text: "Отменить"
                        color: cancelApplyMouse.containsMouse ? root.danger : root.muted
                        font.pixelSize: 11
                        font.bold: true
                    }

                    MouseArea {
                        id: cancelApplyMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.cancelTask()
                    }
                }
            }
        }

        // -------------------------------------------------------------
        // STAGE 5: DONE / 1-CLICK EXPORT
        // -------------------------------------------------------------
        Item {
            anchors.fill: parent
            visible: root.phase === "done"

            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 60, 680)
                spacing: 16

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 72
                    height: 72
                    radius: 36
                    color: "#ecfdf5"
                    border.color: "#a7f3d0"
                    border.width: 2

                    Text {
                        anchors.centerIn: parent
                        text: "✓"
                        color: root.success
                        font.pixelSize: 36
                        font.bold: true
                    }
                }

                Text {
                    text: "Параметры успешно применены!"
                    color: root.ink
                    font.pixelSize: 24
                    font.bold: true
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Text {
                    text: "Профиль, кинематика 3D/5D, материал и ориентация переданы в STE Slicer. Вы можете сразу запустить слайсинг или экспортировать артефакты для сдачи.";
                    color: root.muted
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                }

                // Summary Parameter Tiles
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 10

                    Repeater {
                        model: [
                            ["Режим печати", activeCtrl ? activeCtrl.printMode : "5D"],
                            ["Материал", activeCtrl ? activeCtrl.material : "PA6-CF"],
                            ["Слой", activeCtrl ? activeCtrl.layerHeight : "0.20 мм"],
                            ["Заполнение", activeCtrl ? activeCtrl.infillDensity : "50%"]
                        ]

                        delegate: Rectangle {
                            width: 140
                            height: 52
                            radius: 8
                            color: "#ffffff"
                            border.color: root.border
                            border.width: 1

                            Column {
                                anchors.centerIn: parent
                                spacing: 2
                                Text {
                                    text: modelData[0]
                                    color: root.muted
                                    font.pixelSize: 9
                                    anchors.horizontalCenter: parent.horizontalCenter
                                }
                                Text {
                                    text: modelData[1]
                                    color: root.ink
                                    font.pixelSize: 12
                                    font.bold: true
                                    anchors.horizontalCenter: parent.horizontalCenter
                                }
                            }
                        }
                    }
                }

                // 1-Click Export Box (Hackathon artifact generation)
                Rectangle {
                    width: parent.width
                    height: 84
                    radius: 10
                    color: "#eff6ff"
                    border.color: "#bfdbfe"
                    border.width: 1

                    Column {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 8

                        RowLayout {
                            width: parent.width

                            Column {
                                Text {
                                    text: "Экспорт результатов для сдачи (Hackathon results/)"
                                    color: "#1e3a8a"
                                    font.pixelSize: 12
                                    font.bold: true
                                }
                                Text {
                                    text: "Автоматически сохранит project.3mf, result.gcode и скриншот диалога в results/<model>/"
                                    color: "#3b82f6"
                                    font.pixelSize: 10
                                }
                            }

                            Item { Layout.fillWidth: true }

                            Rectangle {
                                height: 34
                                radius: 6
                                color: exportBtnMouse.containsMouse ? "#1d4ed8" : "#2563eb"
                                implicitWidth: exportBtnText.width + 24

                                Row {
                                    id: exportBtnText
                                    anchors.centerIn: parent
                                    spacing: 6
                                    Text { text: "🚀"; font.pixelSize: 12 }
                                    Text {
                                        text: "Экспортировать всё"
                                        color: "#ffffff"
                                        font.pixelSize: 11
                                        font.bold: true
                                    }
                                }

                                MouseArea {
                                    id: exportBtnMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (activeCtrl) activeCtrl.exportResult("model_submission");
                                    }
                                }
                            }
                        }

                        Text {
                            visible: activeCtrl && activeCtrl.exportedDirectory
                            text: activeCtrl && activeCtrl.exportedDirectory ? "Путь: " + activeCtrl.exportedDirectory : ""
                            color: "#1e40af"
                            font.pixelSize: 10
                            elide: Text.ElideMiddle
                            width: parent.width
                        }

                        // Export Success Notification Banner
                        Row {
                            id: exportNoticeBanner
                            visible: activeCtrl && activeCtrl.exportedDirectory ? true : false
                            spacing: 8
                            anchors.horizontalCenter: parent.horizontalCenter

                            Text {
                                id: exportNoticeText
                                text: activeCtrl && activeCtrl.exportStatus ? activeCtrl.exportStatus : "✓ Файлы успешно сформированы"
                                color: "#065f46"
                                font.pixelSize: 10
                                font.bold: true
                            }

                            Text {
                                text: "📂 [Открыть папку]"
                                color: "#2563eb"
                                font.pixelSize: 10
                                font.bold: true
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        if (activeCtrl) activeCtrl.openFolder("");
                                    }
                                }
                            }
                        }
                    }
                }

                // Bottom Action Buttons
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 12

                    Rectangle {
                        width: 160
                        height: 38
                        radius: 8
                        color: doneCloseMouse.containsMouse ? "#1d4ed8" : "#2563eb"

                        Text {
                            anchors.centerIn: parent
                            text: "Перейти в STE Slicer"
                            color: "#ffffff"
                            font.pixelSize: 12
                            font.bold: true
                        }

                        MouseArea {
                            id: doneCloseMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.close()
                        }
                    }

                    Rectangle {
                        width: 170
                        height: 38
                        radius: 8
                        color: newModelMouse.containsMouse ? "#e2e8f0" : "#f1f5f9"
                        border.color: "#cbd5e1"
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: "Подготовить новую деталь"
                            color: root.bodyText
                            font.pixelSize: 11
                            font.bold: true
                        }

                        MouseArea {
                            id: newModelMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.resetToUpload()
                        }
                    }
                }
            }
        }

        // -------------------------------------------------------------
        // STAGE 6: ERROR HANDLER
        // -------------------------------------------------------------
        Item {
            anchors.fill: parent
            visible: root.phase === "error"

            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 80, 560)
                spacing: 14

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 64
                    height: 64
                    radius: 32
                    color: root.dangerSoft
                    border.color: "#fca5a5"
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: "!"
                        color: root.danger
                        font.pixelSize: 32
                        font.bold: true
                    }
                }

                Text {
                    text: "Не удалось выполнить операцию"
                    color: root.ink
                    font.pixelSize: 22
                    font.bold: true
                    anchors.horizontalCenter: parent.horizontalCenter
                }

                Text {
                    text: root.lastError
                    color: root.muted
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                }

                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 10

                    Rectangle {
                        height: 36
                        radius: 6
                        color: errSettingsMouse.containsMouse ? "#e2e8f0" : "#f1f5f9"
                        border.color: "#cbd5e1"
                        border.width: 1
                        implicitWidth: errSettingsText.width + 24

                        Text {
                            id: errSettingsText
                            anchors.centerIn: parent
                            text: "⚙ Проверить настройки LLM"
                            color: root.bodyText
                            font.pixelSize: 11
                            font.bold: true
                        }

                        MouseArea {
                            id: errSettingsMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { if (activeMgr) activeMgr.showSettingsDialog(); }
                        }
                    }

                    Rectangle {
                        height: 36
                        radius: 6
                        color: errRetryMouse.containsMouse ? "#1d4ed8" : "#2563eb"
                        implicitWidth: errRetryText.width + 24

                        Text {
                            id: errRetryText
                            anchors.centerIn: parent
                            text: "Начать заново"
                            color: "#ffffff"
                            font.pixelSize: 11
                            font.bold: true
                        }

                        MouseArea {
                            id: errRetryMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.resetToUpload()
                        }
                    }
                }
            }
        }
    }

    // =================================================================
    // 4. SLIDE-OUT AGENT MCP LOG DRAWER
    // =================================================================
    AgentLogDrawer {
        id: logDrawer
        anchors.right: parent.right
        anchors.top: contextBar.bottom
        anchors.bottom: parent.bottom
        width: Math.min(480, root.width * 0.44)
        controller: root.activeCtrl
        opened: false
        z: 30
    }
}
