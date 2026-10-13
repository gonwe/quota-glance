import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as Plasma5Support

PlasmoidItem {
    id: root

    property var quotaData: ({})
    readonly property string fetchCommand: Qt.resolvedUrl("../code/fetch.py").toString().replace(/^file:\/\//, "")
    readonly property var providerDefinitions: [
        { id: "codex", name: "Codex", configKey: "showCodex" },
        { id: "copilot", name: "GitHub Copilot", configKey: "showCopilot" },
        { id: "zai", name: "Z.ai", configKey: "showZai" },
        { id: "opencode-go", name: "OpenCode Go", configKey: "showOpenCodeGo" },
        { id: "deepseek", name: "DeepSeek", configKey: "showDeepSeek" }
    ]
    readonly property var activeDefinitions: providerDefinitions.filter(function(item) {
        return Boolean(Plasmoid.configuration[item.configKey])
    })
    readonly property var activeProviderIds: activeDefinitions.map(function(item) { return item.id })
    readonly property string currentCommand: fetchCommand + " --providers=" + activeProviderIds.join(",")
    readonly property var providerResults: quotaData.providers || []
    readonly property var activeProviders: activeDefinitions.map(function(definition) {
        const result = root.providerResults.find(function(item) { return item.id === definition.id })
        return {
            id: definition.id,
            name: definition.name,
            ok: result ? result.ok : false,
            error: result ? result.error : "",
            subtitle: result ? result.subtitle : "",
            badge: result ? result.badge : "",
            panelValue: result ? result.panelValue : "",
            metrics: result ? result.metrics : [],
            details: result ? result.details : [],
            description: result ? result.description : ""
        }
    })
    readonly property color secondaryText: Kirigami.Theme.disabledTextColor

    function iconUrl(providerId) {
        return Qt.resolvedUrl("../icons/" + providerId + "-symbolic.svg")
    }

    function formatTime(timestamp) {
        return timestamp ? Qt.formatTime(new Date(timestamp), "HH:mm") : ""
    }

    function acceptOutput(output) {
        try {
            const parsed = JSON.parse(output)
            if (parsed && Array.isArray(parsed.providers))
                quotaData = parsed
        } catch (error) {
            // Keep the last usable snapshot if a command returns malformed output.
        }
    }

    function refreshNow() {
        quotaSource.disconnectSource(currentCommand)
        Qt.callLater(function() {
            if (activeProviderIds.length > 0)
                quotaSource.connectSource(currentCommand)
        })
    }

    function openSettings() {
        const action = Plasmoid.internalAction("configure")
        if (action)
            action.trigger()
    }

    toolTipMainText: "额度速览"
    toolTipSubText: activeProviders.length === 0
        ? "请在设置中选择数据来源"
        : activeProviders.map(function(item) { return item.name }).join(" · ")

    Plasma5Support.DataSource {
        id: quotaSource
        engine: "executable"
        interval: Math.max(1, Number(Plasmoid.configuration.refreshIntervalMinutes || 5)) * 60000
        connectedSources: root.activeProviderIds.length > 0 ? [root.currentCommand] : []

        onNewData: (sourceName, sourceData) => {
            if (sourceName === root.currentCommand && sourceData.stdout)
                root.acceptOutput(sourceData.stdout)
        }
    }

    compactRepresentation: Item {
        id: compactRoot

        implicitWidth: compactRow.implicitWidth + Kirigami.Units.smallSpacing * 2
        implicitHeight: Math.max(compactRow.implicitHeight, Kirigami.Units.iconSizes.small)
        Layout.minimumWidth: implicitWidth
        Layout.preferredWidth: implicitWidth
        Layout.maximumWidth: implicitWidth

        RowLayout {
            id: compactRow
            anchors.centerIn: parent
            spacing: Kirigami.Units.smallSpacing * 1.5

            Repeater {
                model: root.activeProviders

                delegate: RowLayout {
                    required property var modelData
                    spacing: Kirigami.Units.smallSpacing / 2

                    Kirigami.Icon {
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                        source: root.iconUrl(modelData.id)
                        isMask: true
                        color: Kirigami.Theme.textColor
                    }

                    QQC2.Label {
                        text: compactRoot.compactValue(modelData)
                        font.pointSize: 9
                        font.weight: Font.Medium
                        color: Kirigami.Theme.textColor
                    }
                }
            }
        }

        function compactValue(provider) {
            if (!provider.ok)
                return "--"
            return provider.panelValue || (provider.metrics.length > 0 ? provider.metrics[0].value : "--")
        }

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            cursorShape: Qt.PointingHandCursor
            onClicked: root.expanded = !root.expanded
        }
    }

    fullRepresentation: ColumnLayout {
        id: popupRoot
        spacing: Kirigami.Units.smallSpacing
        implicitWidth: 660
        implicitHeight: 520

        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.mediumSpacing

            Kirigami.Icon {
                source: "view-statistics"
                Layout.preferredWidth: Kirigami.Units.iconSizes.large
                Layout.preferredHeight: Kirigami.Units.iconSizes.large
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0

                QQC2.Label {
                    text: "额度速览"
                    font.bold: true
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize + 2
                }

                QQC2.Label {
                    text: root.quotaData.updatedAt
                        ? "更新于 " + root.formatTime(root.quotaData.updatedAt)
                        : "正在等待首次刷新"
                    color: root.secondaryText
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                }
            }

            QQC2.ToolButton {
                icon.name: "view-refresh"
                text: "刷新"
                display: QQC2.AbstractButton.IconOnly
                QQC2.ToolTip.text: "立即刷新"
                QQC2.ToolTip.visible: hovered
                onClicked: root.refreshNow()
            }

            QQC2.ToolButton {
                icon.name: "configure"
                text: "设置"
                display: QQC2.AbstractButton.IconOnly
                QQC2.ToolTip.text: "打开设置"
                QQC2.ToolTip.visible: hovered
                onClicked: root.openSettings()
            }
        }

        Kirigami.Separator {
            Layout.fillWidth: true
        }

        QQC2.ScrollView {
            id: cardsScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth

            GridLayout {
                id: cardsGrid
                width: cardsScroll.availableWidth
                columns: width >= 570 ? 2 : 1
                columnSpacing: Kirigami.Units.smallSpacing
                rowSpacing: Kirigami.Units.smallSpacing

                Repeater {
                    model: root.activeProviders

                    delegate: Rectangle {
                        id: providerCard
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: cardsGrid.columns === 2 ? (cardsGrid.width - cardsGrid.columnSpacing) / 2 : cardsGrid.width
                        Layout.alignment: Qt.AlignTop
                        implicitHeight: cardContent.implicitHeight + Kirigami.Units.largeSpacing * 2
                        radius: Kirigami.Units.cornerRadius
                        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.045)
                        border.width: 1
                        border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.10)

                        ColumnLayout {
                            id: cardContent
                            anchors.fill: parent
                            anchors.margins: Kirigami.Units.mediumSpacing
                            spacing: Kirigami.Units.smallSpacing

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Kirigami.Units.smallSpacing

                                Kirigami.Icon {
                                    source: root.iconUrl(providerCard.modelData.id)
                                    isMask: true
                                    color: Kirigami.Theme.textColor
                                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                                    Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                                }

                                QQC2.Label {
                                    Layout.fillWidth: true
                                    text: providerCard.modelData.name
                                    font.bold: true
                                    elide: Text.ElideRight
                                }

                                QQC2.Label {
                                    visible: providerCard.modelData.badge.length > 0
                                    text: providerCard.modelData.badge
                                    color: root.secondaryText
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    elide: Text.ElideRight
                                }
                            }

                            QQC2.Label {
                                visible: providerCard.modelData.subtitle.length > 0
                                Layout.fillWidth: true
                                text: providerCard.modelData.subtitle
                                color: root.secondaryText
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                                elide: Text.ElideRight
                            }

                            QQC2.Label {
                                visible: !providerCard.modelData.ok && providerCard.modelData.error.length > 0
                                Layout.fillWidth: true
                                text: providerCard.modelData.error
                                wrapMode: Text.WordWrap
                                color: Kirigami.Theme.neutralTextColor
                            }

                            Repeater {
                                model: providerCard.modelData.metrics

                                delegate: ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: 2

                                    RowLayout {
                                        Layout.fillWidth: true

                                        QQC2.Label {
                                            Layout.fillWidth: true
                                            text: modelData.label
                                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                                        }

                                        QQC2.Label {
                                            text: modelData.value
                                            font.bold: true
                                        }
                                    }

                                    QQC2.ProgressBar {
                                        Layout.fillWidth: true
                                        visible: modelData.progress !== null && modelData.progress !== undefined
                                        from: 0
                                        to: 1
                                        value: modelData.progress === null ? 0 : modelData.progress
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        visible: Boolean((modelData.detail && modelData.detail.length > 0) || modelData.resetAt)

                                        QQC2.Label {
                                            Layout.fillWidth: true
                                            text: modelData.detail || ""
                                            color: root.secondaryText
                                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                                            elide: Text.ElideRight
                                        }

                                        QQC2.Label {
                                            visible: Boolean(modelData.resetAt)
                                            text: modelData.resetAt ? "重置于 " + root.formatTime(modelData.resetAt) : ""
                                            color: root.secondaryText
                                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                                        }
                                    }
                                }
                            }

                            Repeater {
                                model: providerCard.modelData.details

                                delegate: QQC2.Label {
                                    required property string modelData
                                    Layout.fillWidth: true
                                    text: modelData
                                    wrapMode: Text.WordWrap
                                    color: root.secondaryText
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                }
                            }
                        }
                    }
                }

                QQC2.Label {
                    Layout.fillWidth: true
                    Layout.columnSpan: cardsGrid.columns
                    visible: root.activeProviders.length === 0
                    text: "尚未选择数据来源。打开设置以选择要显示的服务。"
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                    color: root.secondaryText
                }
            }
        }
    }
}
