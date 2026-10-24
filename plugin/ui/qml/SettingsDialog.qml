import QtQuick 2.7
import QtQuick.Controls 1.4
import QtQuick.Controls.Styles 1.4
import QtQuick.Layouts 1.1
import QtQuick.Window 2.2

Window {
    id: root
    objectName: "settingsDialog"
    title: "Настройки подключения LLM API — STE Slicer"
    width: 560
    height: 480
    minimumWidth: 500
    minimumHeight: 440
    color: "#f8fafc"
    flags: Qt.Dialog

    // Safe accessors
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
                    width: 32
                    height: 32
                    radius: 8
                    color: "#e8f0fe"
                    Text {
                        anchors.centerIn: parent
                        text: "⚙"
                        font.pixelSize: 16
                        color: "#1976d2"
                    }
                }

                Column {
                    Text {
                        text: "Настройки LLM API"
                        color: "#1e293b"
                        font.pixelSize: 16
                        font.bold: true
                    }
                    Text {
                        text: "OpenAI, Ollama, LM Studio, vLLM, OpenRouter"
                        color: "#64748b"
                        font.pixelSize: 11
                    }
                }

                Item { Layout.fillWidth: true }

                // =============================================================
                // PROMINENT CLOSE BUTTON (✕) IN DIALOG HEADER
                // =============================================================
                Rectangle {
                    width: 32
                    height: 32
                    radius: 16
                    color: closeDialogMouse.containsMouse ? "#fee2e2" : "#f1f5f9"
                    border.color: closeDialogMouse.containsMouse ? "#fca5a5" : "#cbd5e1"
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.pixelSize: 14
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
                color: "#e2e8f0"
            }

            // Field: Base URL
            Column {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    text: "Base URL (эндпоинт API):"
                    color: "#1e293b"
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
                    text: "Указывайте без /chat/completions на конце."
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
                    color: "#1e293b"
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
                    color: "#1e293b"
                    font.pixelSize: 12
                    font.bold: true
                }

                TextField {
                    id: modelNameInput
                    width: parent.width
                    placeholderText: "gpt-4o-mini, qwen2.5:7b, llama3.1..."
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
                    width: 170
                    height: 36
                    radius: 8
                    color: checkMouse.containsMouse ? "#e8f0fe" : "#f1f5f9"
                    border.color: checkMouse.containsMouse ? "#1976d2" : "#cbd5e1"
                    border.width: 1

                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Text { text: "🔌"; font.pixelSize: 12 }
                        Text {
                            text: "Проверить связь"
                            font.pixelSize: 12
                            font.bold: true
                            color: checkMouse.containsMouse ? "#1976d2" : "#1e293b"
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
                    width: 110
                    height: 36
                    radius: 8
                    color: saveDialogMouse.containsMouse ? "#1565c0" : "#1976d2"

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
                            }
                            root.close()
                        }
                    }
                }
            }
        }
    }
}
