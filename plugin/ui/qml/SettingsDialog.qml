import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Layouts 1.1
import QtQuick.Window 2.2

Window {
    id: root
    objectName: "settingsDialog"
    title: "Настройки подключения LLM API — STE Slicer"
    width: 600
    height: 520
    minimumWidth: 540
    minimumHeight: 480
    color: "#f8fafc"
    flags: Qt.Dialog

    readonly property var activeCtrl: (typeof controller !== "undefined" && controller) ? controller : (typeof chatController !== "undefined" ? chatController : null)
    readonly property var activeMgr: (typeof manager !== "undefined" && manager) ? manager : null

    onVisibleChanged: {
        if (visible && activeCtrl) {
            baseUrlInput.text = activeCtrl.baseUrl || ""
            apiKeyInput.text = activeCtrl.apiKey || ""
            modelNameInput.text = activeCtrl.modelName || ""
            statusBanner.visible = false
        }
    }

    Connections {
        target: activeCtrl
        onSettingsSaved: {
            statusBanner.visible = true
            statusBanner.isError = false
            statusBannerText.text = "✓ Настройки успешно сохранены."
            root.close()
        }
        onSettingsSaveFailed: {
            statusBanner.visible = true
            statusBanner.isError = true
            statusBannerText.text = "✕ Не удалось сохранить настройки: " + message
        }
        onConnectionCheckFinished: {
            var ok = (typeof success !== "undefined") ? success : (typeof arguments !== "undefined" && arguments.length > 0 ? arguments[0] : false)
            var msg = (typeof message !== "undefined") ? message : (typeof arguments !== "undefined" && arguments.length > 1 ? arguments[1] : "")
            statusBanner.visible = true
            statusBanner.isError = !ok
            statusBannerText.text = (ok ? "✓ " : "✕ ") + msg
        }
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 14
        color: "#ffffff"
        radius: 12
        border.color: "#e2e8f0"
        border.width: 1

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            // Header Bar with Title and Close Button
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                Rectangle {
                    width: 34
                    height: 34
                    radius: 8
                    color: "#eff6ff"
                    Text {
                        anchors.centerIn: parent
                        text: "⚙"
                        font.pixelSize: 18
                        color: "#2563eb"
                    }
                }

                Column {
                    Text {
                        text: "Настройки подключения LLM API"
                        color: "#0f172a"
                        font.pixelSize: 15
                        font.bold: true
                    }
                    Text {
                        text: "Совместимо с OpenAI, Ollama, LM Studio, vLLM, DeepSeek"
                        color: "#64748b"
                        font.pixelSize: 11
                    }
                }

                Item { Layout.fillWidth: true }

                Rectangle {
                    width: 30
                    height: 30
                    radius: 15
                    color: closeDialogMouse.containsMouse ? "#fee2e2" : "#f1f5f9"
                    border.color: closeDialogMouse.containsMouse ? "#fca5a5" : "#cbd5e1"
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.pixelSize: 12
                        font.bold: true
                        color: closeDialogMouse.containsMouse ? "#ef4444" : "#64748b"
                    }

                    MouseArea {
                        id: closeDialogMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.close()
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: "#f1f5f9"
            }

            // Quick Provider Presets Chips
            Column {
                Layout.fillWidth: true
                spacing: 5

                Text {
                    text: "Быстрый выбор провайдера:"
                    color: "#64748b"
                    font.pixelSize: 11
                    font.bold: true
                }

                Flow {
                    width: parent.width
                    spacing: 6

                    Repeater {
                        model: [
                            { label: "🟣 OpenAI", url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
                            { label: "🟠 Ollama (Local)", url: "http://localhost:11434/v1", model: "llama3.1" },
                            { label: "🟢 LM Studio", url: "http://localhost:1234/v1", model: "local-model" },
                            { label: "🔴 DeepSeek", url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
                            { label: "🔵 OpenRouter", url: "https://openrouter.ai/api/v1", model: "anthropic/claude-3.5-sonnet" }
                        ]

                        delegate: Rectangle {
                            height: 24
                            radius: 12
                            color: presetMouse.containsMouse ? "#dbeafe" : "#f1f5f9"
                            border.color: presetMouse.containsMouse ? "#2563eb" : "#e2e8f0"
                            border.width: 1
                            implicitWidth: presetText.width + 16

                            Text {
                                id: presetText
                                anchors.centerIn: parent
                                text: modelData.label
                                font.pixelSize: 10
                                color: "#1e293b"
                            }

                            MouseArea {
                                id: presetMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    baseUrlInput.text = modelData.url;
                                    modelNameInput.text = modelData.model;
                                    if (modelData.label.indexOf("Local") !== -1 || modelData.label.indexOf("LM Studio") !== -1) {
                                        if (!apiKeyInput.text) apiKeyInput.text = "dummy";
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Field: Base URL
            Column {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    text: "Base URL (эндпоинт API):"
                    color: "#0f172a"
                    font.pixelSize: 12
                    font.bold: true
                }

                TextField {
                    id: baseUrlInput
                    width: parent.width
                    placeholderText: "https://api.openai.com/v1 или http://localhost:11434/v1"
                    text: activeCtrl ? activeCtrl.baseUrl : ""
                    font.pixelSize: 12
                }

                Text {
                    text: "Без /chat/completions на конце"
                    color: "#94a3b8"
                    font.pixelSize: 10
                }
            }

            // Field: API Key
            Column {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    text: "API Key (ключ авторизации):"
                    color: "#0f172a"
                    font.pixelSize: 12
                    font.bold: true
                }

                RowLayout {
                    width: parent.width
                    spacing: 6

                    TextField {
                        id: apiKeyInput
                        Layout.fillWidth: true
                        placeholderText: "sk-... (для локальных LLM укажите 'dummy')"
                        echoMode: showKeyBtn.checked ? TextInput.Normal : TextInput.Password
                        text: activeCtrl ? activeCtrl.apiKey : ""
                        font.pixelSize: 12
                    }

                    Rectangle {
                        id: showKeyBtn
                        property bool checked: false
                        width: 32
                        height: 32
                        radius: 6
                        color: showKeyMouse.containsMouse ? "#e2e8f0" : "#f1f5f9"
                        border.color: "#cbd5e1"
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: showKeyBtn.checked ? "👁" : "🔒"
                            font.pixelSize: 13
                        }

                        MouseArea {
                            id: showKeyMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: showKeyBtn.checked = !showKeyBtn.checked
                        }
                    }
                }
            }

            // Field: Model Name
            Column {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    text: "Название модели:"
                    color: "#0f172a"
                    font.pixelSize: 12
                    font.bold: true
                }

                TextField {
                    id: modelNameInput
                    width: parent.width
                    placeholderText: "gpt-4o-mini, llama3.1, deepseek-chat..."
                    text: activeCtrl ? activeCtrl.modelName : ""
                    font.pixelSize: 12
                }
            }

            // Status Alert Feedback Banner
            Rectangle {
                id: statusBanner
                property bool isError: false
                Layout.fillWidth: true
                Layout.preferredHeight: statusBannerText.implicitHeight + 16
                visible: false
                radius: 8
                color: isError ? "#fef2f2" : "#ecfdf5"
                border.color: isError ? "#fca5a5" : "#a7f3d0"
                border.width: 1

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8

                    Text {
                        id: statusBannerText
                        Layout.fillWidth: true
                        text: ""
                        color: statusBanner.isError ? "#991b1b" : "#065f46"
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                    }
                }
            }

            Item { Layout.fillHeight: true }

            // Action Buttons
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                // Check Connection Button
                Rectangle {
                    width: 174
                    height: 36
                    radius: 8
                    color: checkMouse.containsMouse ? "#eff6ff" : "#f1f5f9"
                    border.color: checkMouse.containsMouse ? "#2563eb" : "#cbd5e1"
                    border.width: 1

                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Text { text: "🔌"; font.pixelSize: 12 }
                        Text {
                            text: "Проверить связь"
                            font.pixelSize: 12
                            font.bold: true
                            color: checkMouse.containsMouse ? "#2563eb" : "#1e293b"
                        }
                    }

                    MouseArea {
                        id: checkMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            statusBanner.visible = true
                            statusBanner.isError = false
                            statusBannerText.text = "⟳ Проверка соединения с LLM API..."
                            if (activeCtrl) {
                                activeCtrl.checkConnection(baseUrlInput.text.trim(), apiKeyInput.text.trim(), modelNameInput.text.trim())
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                // Cancel Button
                Rectangle {
                    width: 86
                    height: 36
                    radius: 8
                    color: cancelDialogMouse.containsMouse ? "#f1f5f9" : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: "Отмена"
                        font.pixelSize: 12
                        color: "#64748b"
                    }

                    MouseArea {
                        id: cancelDialogMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.close()
                    }
                }

                // Save Button
                Rectangle {
                    width: 120
                    height: 36
                    radius: 8
                    color: saveDialogMouse.containsMouse ? "#1d4ed8" : "#2563eb"

                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Text { text: "✓"; font.bold: true; color: "#ffffff"; font.pixelSize: 12 }
                        Text {
                            text: "Сохранить"
                            font.bold: true
                            font.pixelSize: 12
                            color: "#ffffff"
                        }
                    }

                    MouseArea {
                        id: saveDialogMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (activeCtrl) {
                                activeCtrl.saveSettings(baseUrlInput.text.trim(), apiKeyInput.text.trim(), modelNameInput.text.trim())
                            } else {
                                statusBanner.visible = true
                                statusBanner.isError = true
                                statusBannerText.text = "✕ Контроллер настроек недоступен."
                            }
                        }
                    }
                }
            }
        }
    }
}
