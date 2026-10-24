import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Dialogs 1.2
import QtQuick.Layouts 1.1
import QtQuick.Window 2.2

/*
 * Focused workflow window for the hackathon scenario:
 *
 *   upload and goal -> analysis -> recommendation + AI clarification
 *   -> applying settings -> done
 *
 * This is intentionally a separate horizontal Window, not a full chat
 * dashboard. AgentLogDrawer remains available for transparent MCP traces.
 */
Window {
    id: root
    objectName: "chatWindow"
    title: "STE Slicer · AI Assistant"
    width: 1120
    height: 700
    minimumWidth: 960
    minimumHeight: 600
    color: "#f3f7fa"
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint

    readonly property color ink: "#263746"
    readonly property color muted: "#748694"
    readonly property color border: "#d5e1e8"
    readonly property color primary: "#147db8"
    readonly property color primarySoft: "#e7f5fb"
    readonly property color success: "#159a68"
    readonly property color warning: "#a96d17"
    readonly property color danger: "#c94b50"

    readonly property var activeCtrl: (typeof controller !== "undefined" && controller) ? controller : null
    readonly property var activeMgr: (typeof manager !== "undefined" && manager) ? manager : null

    property string phase: "upload"
    property string lastError: ""
    property string analysisTitle: "Ожидаем запуск анализа"
    property string analysisDetail: "После запуска проверим модель и доступные режимы печати."
    property int analysisIndex: 0
    property int applyIndex: 0
    property var selectedGoal: "Максимальная прочность"
    property var goals: ["Максимальная прочность", "Быстрая печать", "Высокое качество", "Минимум поддержек"]
    property var analysisNames: [
        "Габариты и масштаб модели",
        "Нависающие элементы и внутренние каналы",
        "Печатаемость в режимах 3D / 5D",
        "Материал и профиль принтера",
        "Ориентация и поддержка"
    ]
    property var applyNames: [
        "Режим печати",
        "Материал",
        "Профиль качества",
        "Ориентация модели",
        "Поддержки и параметры"
    ]

    property int elapsedSec: 0
    property int finishedTools: 0
    property var toolTitles: {
        "analyze_mesh_geometry": "Анализ геометрии модели",
        "select_print_mode_and_profile": "Подбор режима и профиля",
        "modify_scene_and_parameters": "Изменение ориентации и параметров",
        "run_slicing_and_generate_gcode": "Слайсинг и расчёт G-code",
        "validate_and_export_artifacts": "Проверка и экспорт результата"
    }

    function fileCount() {
        return activeCtrl ? activeCtrl.modelCount : 0
    }

    function toolTitle(name) {
        return toolTitles[name] || name || "Шаг агента"
    }

    function elapsedText() {
        var m = Math.floor(elapsedSec / 60)
        var s = elapsedSec % 60
        return m + ":" + (s < 10 ? "0" : "") + s
    }

    function stepStatus(i, current) {
        if (i < current) return "done"
        if (i === current) return "active"
        return "wait"
    }

    function cancelTask() {
        if (activeCtrl) activeCtrl.cancelRequest()
        phase = phase === "apply" ? "recommend" : "upload"
    }

    onVisibleChanged: {
        if (visible && activeCtrl) activeCtrl.refreshPreview()
    }

    Timer {
        interval: 1000
        repeat: true
        running: (root.phase === "analyze" || root.phase === "apply") && activeCtrl && activeCtrl.busy
        onTriggered: root.elapsedSec += 1
    }

    function submitPrompt(text) {
        if (!activeCtrl || !text || text.trim().length === 0) return
        activeCtrl.sendPrompt(text.trim())
    }

    function startAnalysis() {
        if (!activeCtrl || fileCount() === 0 || activeCtrl.busy) return
        analysisIndex = 0
        elapsedSec = 0
        finishedTools = 0
        changeMessages.clear()
        analysisTitle = "Подготовка анализа"
        analysisDetail = "Передаём модель и задачу агенту…"
        phase = "analyze"
        submitPrompt("Проанализируй прикреплённую модель для печати. Цель: " + selectedGoal + ". " + customGoal.text + ". Определи режим 3D/5D, материал, профиль, ориентацию, поддержки и подготовь аргументированную рекомендацию. Пока не применяй изменения, не запускай слайсинг и экспорт: используй только анализ геометрии и подбор профиля.")
    }

    function askChange(text) {
        if (!activeCtrl || !text || text.trim().length === 0 || activeCtrl.busy) return
        changeMessages.append({"role": "user", "text": text.trim()})
        changeInput.text = ""
        submitPrompt("Измени текущую рекомендацию по запросу пользователя: " + text.trim() + ". Верни обновлённые параметры и объясни последствия, но не применяй их пока.")
    }

    function applyRecommendation() {
        if (!activeCtrl || activeCtrl.busy) return
        applyIndex = 0
        elapsedSec = 0
        phase = "apply"
        submitPrompt("Примени текущую подтверждённую рекомендацию к STE Slicer: режим печати, материал, профиль, ориентацию модели, поддержки и параметры. Не запускай слайсинг. После применения сообщи результат.")
    }

    function setAnalysisStep(toolName) {
        if (phase !== "analyze") return
        analysisIndex = Math.min(4, analysisIndex + 1)
        analysisTitle = toolTitle(toolName)
        analysisDetail = "Выполняется MCP-инструмент " + toolName
    }

    function finishPhase(text) {
        if (phase === "analyze") {
            analysisIndex = 5
            if (text) changeMessages.append({"role": "assistant", "text": text})
            phase = "recommend"
        } else if (phase === "apply") {
            applyIndex = 5
            phase = "done"
        } else if (phase === "recommend" && text) {
            changeMessages.append({"role": "assistant", "text": text})
        }
    }

    function setApplyStep(label) {
        if (phase !== "apply") return
        applyIndex = Math.min(4, applyIndex + 1)
    }

    function resetToUpload() {
        if (activeCtrl && !activeCtrl.busy) activeCtrl.clearConversation()
        phase = "upload"
        lastError = ""
        analysisIndex = 0
        applyIndex = 0
    }

    FileDialog {
        id: modelDialog
        title: "Выберите 3D-модель"
        selectMultiple: true
        nameFilters: ["3D-модели (*.stl *.obj *.3mf)", "Все поддерживаемые файлы (*.stl *.obj *.3mf)"]
        onAccepted: {
            if (activeCtrl) {
                for (var i = 0; i < fileUrls.length; i++) activeCtrl.addAttachment(fileUrls[i].toString())
            }
        }
    }

    ListModel { id: changeMessages }

    Connections {
        target: activeCtrl

        onMessageAdded: {
            // The workflow screens intentionally do not expose the full
            // conversation list. Detailed messages remain available in the
            // agent log and in the controller's MessageListModel.
        }
        onTaskStarted: {
            if (root.phase === "analyze") {
                root.analysisTitle = "Запущен анализ модели"
                root.analysisDetail = "Агент собирает данные о геометрии…"
            } else if (root.phase === "apply") {
                root.analysisTitle = "Применяем настройки"
            }
        }
        // toolStarted(toolName, callId): the second argument is an opaque
        // call id like "call_624a…", so only the tool name is shown.
        onToolStarted: {
            if (root.phase === "analyze") root.setAnalysisStep(arguments[0])
            if (root.phase === "apply") root.setApplyStep(arguments[0])
        }
        onToolFinished: {
            root.finishedTools += 1
            if (root.phase === "analyze") root.analysisDetail = "Агент обдумывает результаты и выбирает следующий шаг…"
        }
        onResponseReady: root.finishPhase(arguments[0])
        // An empty final answer emits only taskFinished; without this the
        // window stayed on the analysis screen forever.
        onTaskFinished: {
            if (root.phase === "analyze" || root.phase === "apply") root.finishPhase("")
        }
        onTaskFailed: {
            root.lastError = arguments[0] || "Не удалось выполнить операцию."
            root.phase = "error"
        }
    }

    Rectangle {
        id: header
        anchors.top: parent.top
        width: parent.width
        height: 62
        color: "#ffffff"
        border.color: root.border

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 24
            anchors.rightMargin: 18
            spacing: 12

            Text { text: "✣"; color: root.primary; font.pixelSize: 28 }
            Column {
                spacing: 2
                Text { text: "slicer assistant"; color: "#526b7d"; font.pixelSize: 20 }
                Text { text: "STE Slicer · подготовка печати"; color: root.muted; font.pixelSize: 10 }
            }
            Item { Layout.fillWidth: true }
            Rectangle {
                height: 28
                radius: 14
                color: "#f2faf6"
                border.color: "#bfe6d3"
                implicitWidth: statusText.width + 30
                Row {
                    anchors.centerIn: parent
                    spacing: 7
                    Rectangle { width: 7; height: 7; radius: 4; color: activeCtrl && activeCtrl.connected ? root.success : root.warning; anchors.verticalCenter: parent.verticalCenter }
                    Text { id: statusText; text: activeCtrl && activeCtrl.connected ? "STE Slicer подключен" : "Подключение…"; color: root.muted; font.pixelSize: 11 }
                }
            }
            Button { text: "Настройки"; onClicked: { if (activeMgr) activeMgr.showSettingsDialog() } }
            Button { text: "×"; onClicked: root.close() }
        }
    }

    Rectangle {
        id: contextBar
        anchors.top: header.bottom
        width: parent.width
        height: 42
        color: "#edf5f9"
        border.color: root.border
        Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 24
            spacing: 22
            Text { text: "Принтер: " + (activeCtrl ? activeCtrl.printerName : "Stereotech Hybrid 530"); color: root.ink; font.pixelSize: 11 }
            Text { text: "Режим: " + (activeCtrl ? activeCtrl.printMode : "3D"); color: root.ink; font.pixelSize: 11 }
            Text { text: "Материал: " + (activeCtrl ? activeCtrl.material : "не выбран"); color: root.ink; font.pixelSize: 11 }
            Text { text: "Моделей: " + fileCount(); color: root.ink; font.pixelSize: 11 }
        }
    }

    Item {
        id: body
        anchors.top: contextBar.bottom
        anchors.bottom: parent.bottom
        width: parent.width

        // ---------------------------------------------------------------
        // 1. MODEL + GOAL
        // ---------------------------------------------------------------
        Item {
            anchors.fill: parent
            visible: root.phase === "upload"

            Column {
                anchors.fill: parent
                anchors.margins: 28
                spacing: 12

                Text { text: "Подготовим модель к печати"; color: root.ink; font.pixelSize: 24; font.bold: true }
                Text { text: "Загрузите модель и укажите, что важно получить. Ассистент подберёт настройки, но ничего не применит без вашего подтверждения."; color: root.muted; font.pixelSize: 12 }

                Row {
                    width: parent.width
                    height: parent.height - 135
                    spacing: 22

                    Rectangle {
                        width: parent.width * 0.52
                        height: parent.height
                        radius: 10
                        color: dropArea.containsDrag ? "#e7f5fb" : "#fbfdfe"
                        border.color: dropArea.containsDrag ? root.primary : "#9ebdce"
                        border.width: dropArea.containsDrag ? 2 : 1

                        Column {
                            anchors.centerIn: parent
                            spacing: 9
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "⇧"; color: root.primary; font.pixelSize: 38 }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Перетащите 3D-модель сюда"; color: root.ink; font.pixelSize: 16; font.bold: true }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "или"; color: root.muted; font.pixelSize: 11 }
                            Button { anchors.horizontalCenter: parent.horizontalCenter; text: "Выбрать файл"; onClicked: modelDialog.open() }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "STL · OBJ · 3MF"; color: root.muted; font.pixelSize: 10 }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; visible: fileCount() > 0; text: "Моделей готово к анализу: " + fileCount(); color: root.success; font.pixelSize: 11 }
                        }
                        DropArea {
                            id: dropArea
                            anchors.fill: parent
                            onDropped: {
                                if (drop.hasUrls && activeCtrl) {
                                    for (var i = 0; i < drop.urls.length; i++) activeCtrl.addAttachment(drop.urls[i].toString())
                                }
                            }
                        }
                    }

                    Column {
                        width: parent.width * 0.48 - 22
                        height: parent.height
                        spacing: 10
                        Text { text: "Цель печати"; color: root.ink; font.pixelSize: 14; font.bold: true }
                        Text { text: "Выберите вариант или сформулируйте задачу своими словами"; color: root.muted; font.pixelSize: 10 }
                        Grid {
                            columns: 2
                            spacing: 8
                            width: parent.width
                            Repeater {
                                model: root.goals
                                delegate: Rectangle {
                                    width: (parent.width - 8) / 2
                                    height: 58
                                    radius: 7
                                    color: root.selectedGoal === modelData ? root.primarySoft : "#ffffff"
                                    border.color: root.selectedGoal === modelData ? root.primary : root.border
                                    Text { anchors.centerIn: parent; text: modelData; color: root.selectedGoal === modelData ? root.primary : root.ink; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; width: parent.width - 10; wrapMode: Text.Wrap }
                                    MouseArea { anchors.fill: parent; onClicked: root.selectedGoal = modelData }
                                }
                            }
                        }
                        Rectangle {
                            width: parent.width
                            height: 76
                            radius: 7
                            color: "#ffffff"
                            border.color: customGoal.activeFocus ? root.primary : root.border
                            Text { anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 10; text: "✦"; color: root.warning; font.pixelSize: 17 }
                            TextArea { id: customGoal; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.leftMargin: 34; anchors.rightMargin: 8; anchors.topMargin: 8; anchors.bottomMargin: 5; frameVisible: false; wrapMode: TextEdit.Wrap; font.pixelSize: 11 }
                            Text { anchors.left: parent.left; anchors.top: parent.top; anchors.leftMargin: 38; anchors.topMargin: 12; visible: customGoal.text.length === 0 && !customGoal.activeFocus; text: "Например: кронштейн под нагрузку, PETG, без поддержек"; color: root.muted; font.pixelSize: 11 }
                        }
                        AttachmentBar { width: parent.width; controller: root.activeCtrl; attachmentModel: activeCtrl ? activeCtrl.attachmentModel : null }
                    }
                }
            }
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 61
                color: "#ffffff"
                border.color: root.border
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 28
                    anchors.rightMargin: 28
                    Text { text: "AI сначала проанализирует модель и покажет рекомендации"; color: root.muted; font.pixelSize: 10; Layout.fillWidth: true }
                    Button { text: "Проанализировать модель  →"; enabled: fileCount() > 0 && !(activeCtrl && activeCtrl.busy); onClicked: root.startAnalysis() }
                }
            }
        }

        // ---------------------------------------------------------------
        // 2. ANALYSIS
        // ---------------------------------------------------------------
        Item {
            anchors.fill: parent
            anchors.margins: 28
            visible: root.phase === "analyze"
            Column {
                anchors.fill: parent
                spacing: 16
                Text { text: "Анализируем модель"; color: root.ink; font.pixelSize: 24; font.bold: true }
                Text { text: "Ассистент проверяет конкретные ограничения детали и принтера перед подбором профиля."; color: root.muted; font.pixelSize: 12 }
                Row {
                    width: parent.width
                    height: parent.height - 95
                    spacing: 20
                    Rectangle {
                        width: parent.width * 0.42
                        height: parent.height
                        radius: 9
                        color: "#ffffff"
                        border.color: root.border
                        Column {
                            anchors.fill: parent
                            spacing: 0
                            Text { text: "ПРЕДПРОСМОТР МОДЕЛИ"; color: root.muted; font.pixelSize: 10; anchors.left: parent.left; anchors.margins: 14; height: 34; verticalAlignment: Text.AlignVCenter }
                            ModelPreview {
                                width: parent.width
                                height: parent.height - 72
                                controller: root.activeCtrl
                            }
                            Text { text: activeCtrl && activeCtrl.modelInfo ? activeCtrl.modelInfo : "Габариты будут определены агентом"; color: root.muted; font.pixelSize: 10; width: parent.width - 20; anchors.horizontalCenter: parent.horizontalCenter; height: 38; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; maximumLineCount: 2; wrapMode: Text.Wrap }
                        }
                    }
                    Rectangle {
                        width: parent.width * 0.58 - 20
                        height: parent.height
                        radius: 9
                        color: "#ffffff"
                        border.color: root.border
                        Column {
                            anchors.fill: parent
                            anchors.margins: 20
                            spacing: 12
                            Item {
                                width: parent.width
                                height: 22
                                StepIcon { id: headIcon; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; status: activeCtrl && activeCtrl.busy ? "active" : "done"; activeColor: root.primary; doneColor: root.success }
                                Text { anchors.left: headIcon.right; anchors.leftMargin: 8; anchors.right: percentText.left; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: root.analysisTitle; color: root.ink; font.pixelSize: 14; font.bold: true; elide: Text.ElideRight }
                                Text { id: percentText; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: Math.min(100, root.analysisIndex * 20) + "%"; color: root.primary; font.pixelSize: 12; font.bold: true }
                            }
                            Text { text: root.analysisDetail + " · " + root.elapsedText(); color: root.muted; font.pixelSize: 10; wrapMode: Text.Wrap; width: parent.width }
                            ProgressTrack { width: parent.width; value: root.analysisIndex / 5; busy: activeCtrl && activeCtrl.busy; barColor: root.primary }
                            Column {
                                width: parent.width
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
                            Text {
                                width: parent.width
                                visible: root.elapsedSec >= 45 && activeCtrl && activeCtrl.busy
                                text: "Ответ нейросети занимает больше обычного. Каждый шаг агента — отдельный запрос к LLM, на медленном API это может занять 1–2 минуты."
                                color: root.warning
                                font.pixelSize: 10
                                wrapMode: Text.Wrap
                            }
                            Button { text: "Отменить анализ"; visible: activeCtrl && activeCtrl.busy; onClicked: root.cancelTask() }
                        }
                    }
                }
            }
        }

        // ---------------------------------------------------------------
        // 3. RECOMMENDATION + AI CHANGE PANEL
        // ---------------------------------------------------------------
        Item {
            anchors.fill: parent
            anchors.margins: 24
            visible: root.phase === "recommend"
            Column {
                anchors.fill: parent
                spacing: 10
                Row {
                    width: parent.width
                    Text { text: "Профиль печати готов"; color: root.ink; font.pixelSize: 22; font.bold: true }
                    Item { width: parent.width - 300; height: 1 }
                    Rectangle { width: 150; height: 25; radius: 5; color: "#e5f6ee"; Text { anchors.centerIn: parent; text: "✓ Готово к применению"; color: root.success; font.pixelSize: 10; font.bold: true } }
                }
                Text { text: "Проверьте рекомендации. Вы можете попросить AI изменить их перед применением."; color: root.muted; font.pixelSize: 11 }
                Row {
                    width: parent.width
                    height: parent.height - 105
                    spacing: 12
                    Rectangle {
                        width: parent.width * 0.28
                        height: parent.height
                        radius: 8
                        color: "#ffffff"
                        border.color: root.border
                        Column {
                            anchors.fill: parent
                            Text { text: "ОРИЕНТАЦИЯ МОДЕЛИ"; color: root.muted; font.pixelSize: 9; height: 32; anchors.left: parent.left; anchors.margins: 12; verticalAlignment: Text.AlignVCenter }
                            ModelPreview { width: parent.width; height: parent.height - 75; controller: root.activeCtrl }
                            Text { text: "✦ Ориентация рекомендована AI"; color: root.primary; font.pixelSize: 9; anchors.horizontalCenter: parent.horizontalCenter; height: 42; verticalAlignment: Text.AlignVCenter }
                        }
                    }
                    Rectangle {
                        width: parent.width * 0.37
                        height: parent.height
                        radius: 8
                        color: "#ffffff"
                        border.color: root.border
                        Column {
                            anchors.fill: parent
                            Text { text: "Подобранные характеристики"; color: root.ink; font.pixelSize: 12; font.bold: true; height: 35; anchors.left: parent.left; anchors.margins: 12; verticalAlignment: Text.AlignVCenter }
                            Column {
                                width: parent.width
                                Repeater {
                                    model: [
                                        ["Режим печати", activeCtrl ? activeCtrl.printMode : "3D"],
                                        ["Материал", activeCtrl ? activeCtrl.material : "PP"],
                                        ["Профиль", "High Strength"],
                                        ["Высота слоя", "0,20 мм"],
                                        ["Сопло", "0,6 мм · закалённое"],
                                        ["Температура сопла", "250 °C"],
                                        ["Заполнение", "100%"],
                                        ["Поддержки", "Локальные, съёмные"]
                                    ]
                                    delegate: Rectangle {
                                        width: parent.width
                                        height: 25
                                        color: index % 2 === 0 ? "#f1f7fa" : "#ffffff"
                                        Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: modelData[0]; color: root.muted; font.pixelSize: 10 }
                                        Text { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: modelData[1]; color: index === 0 || index === 1 || index === 6 ? root.primary : root.ink; font.pixelSize: 10; font.bold: index === 0 || index === 1 }
                                    }
                                }
                            }
                            Rectangle { width: parent.width - 20; height: 1; color: root.border; anchors.horizontalCenter: parent.horizontalCenter }
                            Text { text: "Что оптимизировано"; color: "#396c85"; font.pixelSize: 10; font.bold: true; anchors.left: parent.left; anchors.margins: 12; height: 25; verticalAlignment: Text.AlignVCenter }
                            Text { text: "AI учёл геометрию, цель печати и доступные профили. Нажмите «Почему так?» или попросите изменить рекомендацию."; color: root.muted; font.pixelSize: 9; wrapMode: Text.Wrap; width: parent.width - 24; anchors.left: parent.left; anchors.margins: 12 }
                        }
                    }
                    Rectangle {
                        width: parent.width * 0.35 - 24
                        height: parent.height
                        radius: 8
                        color: "#ffffff"
                        border.color: root.border
                        Column {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 7
                            Row {
                                width: parent.width
                                Text { text: "✦"; color: root.warning; font.pixelSize: 18 }
                                Column { Text { text: "Изменить с AI"; color: root.ink; font.pixelSize: 11; font.bold: true }
Text { text: "Спросите или измените настройку"; color: root.muted; font.pixelSize: 9 } }
                            }
                            Button { text: "Почему выбраны эти настройки?"; width: parent.width; onClicked: changeInput.text = "Почему ты выбрал эти настройки?" }
                            Flow {
                                width: parent.width
                                spacing: 4
                                Repeater {
                                    model: ["Быстрее", "Без поддержек", "Режим 5D", "PETG"]
                                    delegate: Button { text: modelData; onClicked: root.askChange(modelData) }
                                }
                            }
                            ListView {
                                id: changeList
                                width: parent.width
                                height: parent.height - 180
                                clip: true
                                spacing: 5
                                model: changeMessages
                                delegate: Rectangle { width: changeList.width; height: changeText.implicitHeight + 14; radius: 6; color: model.role === "user" ? root.primarySoft : "#f6fafc"; border.color: root.border; Text { id: changeText; anchors.fill: parent; anchors.margins: 7; text: model.text; color: root.ink; font.pixelSize: 9; wrapMode: Text.Wrap } }
                            }
                            Row {
                                width: parent.width
                                spacing: 5
                                TextField { id: changeInput; width: parent.width - 38; placeholderText: "Например: заполнение 40%"; font.pixelSize: 10; onAccepted: root.askChange(text) }
                                Button { text: "↑"; width: 32; onClicked: root.askChange(changeInput.text); enabled: !(activeCtrl && activeCtrl.busy) }
                            }
                        }
                    }
                }
                Rectangle { width: parent.width; height: 38; radius: 5; color: "#fff8e8"; border.color: "#f0dcae"; Text { anchors.fill: parent; anchors.margins: 10; text: "⚠ Предварительный профиль требует калибровки и проверки материала перед серийной печатью."; color: root.warning; font.pixelSize: 10; verticalAlignment: Text.AlignVCenter } }
            }
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                height: 58
                color: "#ffffff"
                border.color: root.border
                RowLayout { anchors.fill: parent; anchors.leftMargin: 24; anchors.rightMargin: 24; Button { text: "Изменить задачу"; onClicked: root.resetToUpload() }
Item { Layout.fillWidth: true }
Button { text: "Применить настройки  →"; onClicked: root.applyRecommendation(); enabled: !(activeCtrl && activeCtrl.busy) } }
            }
        }

        // ---------------------------------------------------------------
        // 4. APPLYING
        // ---------------------------------------------------------------
        Item {
            anchors.fill: parent
            anchors.margins: 30
            visible: root.phase === "apply"
            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 80, 720)
                spacing: 16
                Text { text: "Применяем настройки"; color: root.ink; font.pixelSize: 24; font.bold: true; anchors.horizontalCenter: parent.horizontalCenter }
                Text { text: "Передаём выбранный профиль в STE Slicer. Слайсинг не запускается на этом шаге."; color: root.muted; font.pixelSize: 12; anchors.horizontalCenter: parent.horizontalCenter }
                Rectangle {
                    width: parent.width
                    height: applyColumn.implicitHeight + 48
                    radius: 10
                    color: "#ffffff"
                    border.color: root.border
                    Column {
                        id: applyColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 24
                        spacing: 8
                        Item {
                            width: parent.width
                            height: 22
                            StepIcon { id: applyIcon; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; status: activeCtrl && activeCtrl.busy ? "active" : "done"; activeColor: root.primary; doneColor: root.success }
                            Text { anchors.left: applyIcon.right; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter; text: "Применение профиля"; color: root.ink; font.bold: true; font.pixelSize: 13 }
                            Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: Math.min(100, root.applyIndex * 20) + "%"; color: root.primary; font.bold: true; font.pixelSize: 12 }
                        }
                        ProgressTrack { width: parent.width; value: root.applyIndex / 5; busy: activeCtrl && activeCtrl.busy; barColor: root.primary }
                        Repeater {
                            model: root.applyNames
                            delegate: StepRow { width: parent.width; label: modelData; status: root.stepStatus(index, root.applyIndex); inkColor: root.ink; mutedColor: root.muted; primaryColor: root.primary; successColor: root.success }
                        }
                    }
                }
                Text { text: "Прошло " + root.elapsedText(); color: root.muted; font.pixelSize: 10; anchors.horizontalCenter: parent.horizontalCenter }
                Button { text: "Отменить"; anchors.horizontalCenter: parent.horizontalCenter; onClicked: root.cancelTask() }
            }
        }

        // ---------------------------------------------------------------
        // DONE / ERROR
        // ---------------------------------------------------------------
        Item {
            anchors.fill: parent
            visible: root.phase === "done" || root.phase === "error"
            Column {
                anchors.centerIn: parent
                width: Math.min(parent.width - 80, 600)
                spacing: 13
                Text { text: root.phase === "done" ? "✓" : "!"; color: root.phase === "done" ? root.success : root.danger; font.pixelSize: 52; anchors.horizontalCenter: parent.horizontalCenter }
                Text { text: root.phase === "done" ? "Настройки применены" : "Не удалось завершить операцию"; color: root.ink; font.pixelSize: 23; font.bold: true; anchors.horizontalCenter: parent.horizontalCenter }
                Text { text: root.phase === "done" ? "Профиль, материал, режим и ориентация переданы в STE Slicer." : root.lastError; color: root.muted; font.pixelSize: 12; wrapMode: Text.Wrap; width: parent.width; horizontalAlignment: Text.AlignHCenter }
                Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 8; visible: root.phase === "done"; Repeater { model: ["Режим: " + (activeCtrl ? activeCtrl.printMode : "3D"), "Материал: " + (activeCtrl ? activeCtrl.material : "PP"), "Профиль: High Strength"]; delegate: Rectangle { width: 145; height: 42; radius: 6; color: "#ffffff"; border.color: root.border; Text { anchors.centerIn: parent; text: modelData; color: root.ink; font.pixelSize: 10 } } } }
                Row { anchors.horizontalCenter: parent.horizontalCenter; spacing: 8; Button { text: root.phase === "done" ? "Готово" : "Вернуться к рекомендации"; onClicked: root.phase === "done" ? root.close() : root.phase = "recommend" }
Button { visible: root.phase === "error"; text: "Начать заново"; onClicked: root.resetToUpload() } }
            }
        }
    }

    AgentLogDrawer { id: logDrawer; anchors.right: parent.right; anchors.top: contextBar.bottom; anchors.bottom: parent.bottom; width: Math.min(450, root.width * .42); controller: root.activeCtrl; opened: false; z: 20 }
}
