import QtQuick 2.7
import QtQuick.Controls 1.4

/*
 * High-performance Interactive 3D Model Viewport for STE Slicer.
 * Features:
 *  - Live multi-angle camera switching (3D Isometric, Front, Top, Right, Left)
 *  - Interactive mouse wheel zoom and mouse drag orbit
 *  - Zoom In/Out/Reset controls
 *  - Bounding box dimensions & print mode overlay badges
 *  - Animated snapshot refresh indicator
 *  - Expanded inspection modal for high-res examination
 */
Rectangle {
    id: root
    property var controller: null
    property bool allowInteractiveControls: true
    property bool expanded: false
    property string activeAngle: controller ? controller.currentAngle : "3d_isometric"

    readonly property string source: controller ? controller.previewUrl : ""
    readonly property bool hasModel: controller && controller.modelCount > 0
    readonly property string dimsText: controller && controller.dimensionsText ? controller.dimensionsText : ""
    readonly property string printMode: controller ? controller.printMode : "3D"

    color: "#0f172a"
    radius: 10
    border.color: "#334155"
    border.width: 1
    clip: true

    // Background 3D grid lines (CAD/Slicer aesthetic)
    Canvas {
        id: gridCanvas
        anchors.fill: parent
        opacity: 0.22
        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();
            ctx.strokeStyle = "#38bdf8";
            ctx.lineWidth = 1;

            var step = 28;
            for (var x = 0; x < width; x += step) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, height);
                ctx.stroke();
            }
            for (var y = 0; y < height; y += step) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(width, y);
                ctx.stroke();
            }
        }
    }

    // -----------------------------------------------------------------
    // MAIN PREVIEW IMAGE & INTERACTION AREA
    // -----------------------------------------------------------------
    Item {
        id: viewportArea
        anchors.fill: parent
        anchors.margins: 4

        Image {
            id: previewImage
            anchors.fill: parent
            source: root.source
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: false
            smooth: true
            visible: status === Image.Ready && root.hasModel

            // Local zoom and pan support
            property real localZoom: 1.0
            property real panX: 0
            property real panY: 0

            transform: [
                Scale {
                    origin.x: previewImage.width / 2
                    origin.y: previewImage.height / 2
                    xScale: previewImage.localZoom
                    yScale: previewImage.localZoom
                },
                Translate {
                    x: previewImage.panX
                    y: previewImage.panY
                }
            ]

            Behavior on localZoom {
                NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
            }
        }

        // Mouse interaction: Drag to orbit/pan, Wheel to zoom
        MouseArea {
            id: interactionArea
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor

            property real lastX: 0
            property real lastY: 0
            property bool isDragging: false

            onPressed: {
                lastX = mouse.x;
                lastY = mouse.y;
                isDragging = true;
            }

            onPositionChanged: {
                if (!isDragging) return;
                var dx = mouse.x - lastX;
                var dy = mouse.y - lastY;
                lastX = mouse.x;
                lastY = mouse.y;

                if (mouse.buttons === Qt.RightButton) {
                    // Pan
                    previewImage.panX += dx;
                    previewImage.panY += dy;
                } else if (mouse.buttons === Qt.LeftButton) {
                    // Orbit camera via controller (debounced via dispatcher)
                    if (root.controller && Math.abs(dx) + Math.abs(dy) > 3) {
                        orbitTimer.pendingYaw += dx * 0.45;
                        orbitTimer.pendingPitch -= dy * 0.35;
                        orbitTimer.restart();
                    }
                }
            }

            onReleased: {
                isDragging = false;
            }

            onWheel: {
                if (wheel.angleDelta.y > 0) {
                    if (root.controller) root.controller.zoomIn();
                    previewImage.localZoom = Math.min(2.5, previewImage.localZoom * 1.1);
                } else if (wheel.angleDelta.y < 0) {
                    if (root.controller) root.controller.zoomOut();
                    previewImage.localZoom = Math.max(0.7, previewImage.localZoom / 1.1);
                }
            }

            onDoubleClicked: {
                previewImage.localZoom = 1.0;
                previewImage.panX = 0;
                previewImage.panY = 0;
                if (root.controller) root.controller.resetCamera();
            }
        }
    }

    // Debounce timer for camera orbit to prevent flooding Qt thread
    Timer {
        id: orbitTimer
        interval: 120
        repeat: false
        property real pendingYaw: 0
        property real pendingPitch: 0
        onTriggered: {
            if (root.controller && (Math.abs(pendingYaw) > 1 || Math.abs(pendingPitch) > 1)) {
                root.controller.orbitCamera(pendingYaw, pendingPitch);
            }
            pendingYaw = 0;
            pendingPitch = 0;
        }
    }

    // -----------------------------------------------------------------
    // EMPTY STATE (NO MODEL)
    // -----------------------------------------------------------------
    Column {
        anchors.centerIn: parent
        spacing: 12
        visible: !root.hasModel || previewImage.status !== Image.Ready

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 64
            height: 64
            radius: 32
            color: "#1e293b"
            border.color: "#38bdf8"
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: "◈"
                color: "#38bdf8"
                font.pixelSize: 32
            }
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.hasModel ? "Генерация 3D-превью сцены…" : "3D-сцена ожидает модель"
            color: "#f1f5f9"
            font.pixelSize: 13
            font.bold: true
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(root.width - 40, 280)
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: root.hasModel ? (root.controller ? root.controller.modelInfo : "") : "Перетащите файл STL/OBJ/3MF или загрузите модель в STE Slicer"
            color: "#94a3b8"
            font.pixelSize: 11
        }
    }

    // -----------------------------------------------------------------
    // TOP FLOATING GLASS BADGES
    // -----------------------------------------------------------------
    Row {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: 10
        spacing: 8
        visible: root.hasModel

        // 3D / 5D Mode Badge
        Rectangle {
            height: 24
            radius: 12
            color: root.printMode === "5D" ? "#581c87" : "#1e3a8a"
            border.color: root.printMode === "5D" ? "#a855f7" : "#60a5fa"
            border.width: 1
            implicitWidth: modeBadgeRow.width + 16

            Row {
                id: modeBadgeRow
                anchors.centerIn: parent
                spacing: 5
                Text {
                    text: root.printMode === "5D" ? "⚡" : "🧊"
                    font.pixelSize: 11
                }
                Text {
                    text: root.printMode === "5D" ? "5D Stereotech" : "3D Режим"
                    color: "#ffffff"
                    font.pixelSize: 10
                    font.bold: true
                }
            }
        }

        // Bounding Dimensions Badge
        Rectangle {
            visible: root.dimsText.length > 0
            height: 24
            radius: 12
            color: "#1e293b"
            border.color: "#475569"
            border.width: 1
            implicitWidth: dimsRow.width + 16

            Row {
                id: dimsRow
                anchors.centerIn: parent
                spacing: 5
                Text {
                    text: "📐"
                    font.pixelSize: 11
                }
                Text {
                    text: root.dimsText
                    color: "#e2e8f0"
                    font.pixelSize: 10
                    font.bold: true
                }
            }
        }
    }

    // Top-Right Quick Expand Button
    Rectangle {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 10
        width: 28
        height: 28
        radius: 6
        color: expandMouse.containsMouse ? "#334155" : "#1e293b"
        border.color: expandMouse.containsMouse ? "#38bdf8" : "#475569"
        border.width: 1
        visible: root.hasModel

        Text {
            anchors.centerIn: parent
            text: root.expanded ? "⤓" : "⛶"
            color: "#e2e8f0"
            font.pixelSize: 13
        }

        MouseArea {
            id: expandMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.expanded = !root.expanded
        }
    }

    // -----------------------------------------------------------------
    // BOTTOM FLOATING CAMERA ANGLE CONTROLS TOOLBAR
    // -----------------------------------------------------------------
    Rectangle {
        id: cameraBar
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.margins: 10
        height: 32
        radius: 16
        color: "#1e293b"
        border.color: "#334155"
        border.width: 1
        visible: root.hasModel && root.allowInteractiveControls
        implicitWidth: angleRow.width + 12

        Row {
            id: angleRow
            anchors.centerIn: parent
            spacing: 4

            Repeater {
                model: [
                    { id: "3d_isometric", label: "3D", icon: "🔮" },
                    { id: "front", label: "Спереди", icon: "👁" },
                    { id: "top", label: "Сверху", icon: "⬇" },
                    { id: "right", label: "Сбоку", icon: "➡" }
                ]

                delegate: Rectangle {
                    height: 24
                    radius: 12
                    implicitWidth: angleLabel.width + 16
                    color: root.activeAngle === modelData.id ? "#2563eb" : (angleBtnMouse.containsMouse ? "#334155" : "transparent")
                    border.color: root.activeAngle === modelData.id ? "#60a5fa" : "transparent"
                    border.width: 1

                    Row {
                        anchors.centerIn: parent
                        spacing: 3
                        Text {
                            text: modelData.icon
                            font.pixelSize: 10
                        }
                        Text {
                            id: angleLabel
                            text: modelData.label
                            color: root.activeAngle === modelData.id ? "#ffffff" : "#94a3b8"
                            font.pixelSize: 10
                            font.bold: root.activeAngle === modelData.id
                        }
                    }

                    MouseArea {
                        id: angleBtnMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.activeAngle = modelData.id;
                            if (root.controller) root.controller.setCameraAngle(modelData.id);
                        }
                    }
                }
            }
        }
    }

    // -----------------------------------------------------------------
    // BOTTOM RIGHT ZOOM & REFRESH CONTROLS
    // -----------------------------------------------------------------
    Row {
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: 10
        spacing: 6
        visible: root.hasModel && root.allowInteractiveControls

        // Zoom In (+)
        Rectangle {
            width: 28
            height: 28
            radius: 14
            color: zoomInMouse.containsMouse ? "#334155" : "#1e293b"
            border.color: zoomInMouse.containsMouse ? "#38bdf8" : "#475569"
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: "+"
                color: "#e2e8f0"
                font.pixelSize: 14
                font.bold: true
            }

            MouseArea {
                id: zoomInMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (root.controller) root.controller.zoomIn();
                    previewImage.localZoom = Math.min(2.5, previewImage.localZoom * 1.15);
                }
            }
        }

        // Zoom Out (-)
        Rectangle {
            width: 28
            height: 28
            radius: 14
            color: zoomOutMouse.containsMouse ? "#334155" : "#1e293b"
            border.color: zoomOutMouse.containsMouse ? "#38bdf8" : "#475569"
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: "−"
                color: "#e2e8f0"
                font.pixelSize: 14
                font.bold: true
            }

            MouseArea {
                id: zoomOutMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (root.controller) root.controller.zoomOut();
                    previewImage.localZoom = Math.max(0.6, previewImage.localZoom / 1.15);
                }
            }
        }

        // Reset View (⟲)
        Rectangle {
            width: 28
            height: 28
            radius: 14
            color: resetMouse.containsMouse ? "#334155" : "#1e293b"
            border.color: resetMouse.containsMouse ? "#38bdf8" : "#475569"
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: "⟲"
                color: "#e2e8f0"
                font.pixelSize: 13
            }

            MouseArea {
                id: resetMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    previewImage.localZoom = 1.0;
                    previewImage.panX = 0;
                    previewImage.panY = 0;
                    root.activeAngle = "3d_isometric";
                    if (root.controller) root.controller.resetCamera();
                }
            }
        }

        // Refresh Snapshot (↻)
        Rectangle {
            width: 28
            height: 28
            radius: 14
            color: refreshMouse.containsMouse ? "#334155" : "#1e293b"
            border.color: refreshMouse.containsMouse ? "#38bdf8" : "#475569"
            border.width: 1

            Text {
                id: refreshIcon
                anchors.centerIn: parent
                text: "↻"
                color: "#38bdf8"
                font.pixelSize: 14
                font.bold: true
            }

            RotationAnimation {
                id: spinAnim
                target: refreshIcon
                from: 0
                to: 360
                duration: 700
                running: false
            }

            MouseArea {
                id: refreshMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    spinAnim.restart();
                    if (root.controller) root.controller.refreshPreview();
                }
            }
        }
    }

    // -----------------------------------------------------------------
    // EXPANDED INSPECTION MODAL (FULL VIEW)
    // -----------------------------------------------------------------
    Rectangle {
        id: inspectModal
        anchors.fill: parent
        color: "#090d16"
        visible: root.expanded
        z: 99

        Column {
            anchors.fill: parent
            anchors.margins: 14
            spacing: 10

            // Modal Header
            Row {
                width: parent.width
                spacing: 12

                Text {
                    text: "🔍 Детальный 3D-осмотр модели"
                    color: "#f8fafc"
                    font.pixelSize: 15
                    font.bold: true
                    anchors.verticalCenter: parent.verticalCenter
                }

                Item { width: 20; height: 1 }

                Rectangle {
                    height: 22
                    radius: 11
                    color: "#1e293b"
                    border.color: "#475569"
                    implicitWidth: inspectDims.width + 16
                    anchors.verticalCenter: parent.verticalCenter
                    Text {
                        id: inspectDims
                        anchors.centerIn: parent
                        text: root.dimsText ? root.dimsText : "Габариты детали"
                        color: "#38bdf8"
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                Item { width: inspectModal.width - 480; height: 1 }

                Rectangle {
                    width: 26
                    height: 26
                    radius: 13
                    color: closeInspectMouse.containsMouse ? "#ef4444" : "#1e293b"
                    border.color: "#475569"

                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        color: "#ffffff"
                        font.pixelSize: 12
                        font.bold: true
                    }

                    MouseArea {
                        id: closeInspectMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.expanded = false
                    }
                }
            }

            // Big Image
            Image {
                width: parent.width
                height: parent.height - 85
                source: root.source
                fillMode: Image.PreserveAspectFit
                smooth: true
            }

            // Bottom bar with angle triggers in expanded view
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 8

                Repeater {
                    model: [
                        { id: "3d_isometric", label: "Изометрия 3D" },
                        { id: "front", label: "Вид спереди" },
                        { id: "top", label: "Вид сверху" },
                        { id: "right", label: "Вид справа" },
                        { id: "left", label: "Вид слева" }
                    ]

                    delegate: Rectangle {
                        height: 28
                        radius: 14
                        implicitWidth: bigAngleText.width + 20
                        color: root.activeAngle === modelData.id ? "#2563eb" : "#1e293b"
                        border.color: root.activeAngle === modelData.id ? "#60a5fa" : "#334155"

                        Text {
                            id: bigAngleText
                            anchors.centerIn: parent
                            text: modelData.label
                            color: root.activeAngle === modelData.id ? "#ffffff" : "#94a3b8"
                            font.pixelSize: 11
                            font.bold: root.activeAngle === modelData.id
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                root.activeAngle = modelData.id;
                                if (root.controller) root.controller.setCameraAngle(modelData.id);
                            }
                        }
                    }
                }
            }
        }
    }
}
