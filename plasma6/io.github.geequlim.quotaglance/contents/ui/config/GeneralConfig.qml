import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: page

    signal configurationChanged

    property alias cfg_showCodex: codexToggle.checked
    property alias cfg_showCopilot: copilotToggle.checked
    property alias cfg_showZai: zaiToggle.checked
    property alias cfg_showOpenCodeGo: openCodeToggle.checked
    property alias cfg_showDeepSeek: deepSeekToggle.checked
    property alias cfg_refreshIntervalMinutes: refreshInterval.value

    readonly property color subtleText: Kirigami.Theme.disabledTextColor

    Kirigami.FormLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing

        Kirigami.Heading {
            Kirigami.FormData.isSection: true
            text: "数据来源"
        }

        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            text: "选择要显示在面板和额度弹窗中的服务。"
            color: page.subtleText
        }

        RowLayout {
            Kirigami.FormData.label: "Codex"
            Kirigami.Icon {
                source: Qt.resolvedUrl("../../icons/codex-symbolic.svg")
                isMask: true
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            QQC2.CheckBox {
                id: codexToggle
                Layout.fillWidth: true
                text: "Codex CLI 已登录账户的额度"
            }
        }

        RowLayout {
            Kirigami.FormData.label: "GitHub Copilot"
            Kirigami.Icon {
                source: Qt.resolvedUrl("../../icons/copilot-symbolic.svg")
                isMask: true
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            QQC2.CheckBox {
                id: copilotToggle
                Layout.fillWidth: true
                text: "读取 gh 已登录账户的高级请求额度"
            }
        }

        RowLayout {
            Kirigami.FormData.label: "Z.ai"
            Kirigami.Icon {
                source: Qt.resolvedUrl("../../icons/zai-symbolic.svg")
                isMask: true
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            QQC2.CheckBox {
                id: zaiToggle
                Layout.fillWidth: true
                text: "Coding Plan 周期额度"
            }
        }

        RowLayout {
            Kirigami.FormData.label: "OpenCode Go"
            Kirigami.Icon {
                source: Qt.resolvedUrl("../../icons/opencode-go-symbolic.svg")
                isMask: true
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            QQC2.CheckBox {
                id: openCodeToggle
                Layout.fillWidth: true
                text: "工作区用量周期"
            }
        }

        RowLayout {
            Kirigami.FormData.label: "DeepSeek"
            Kirigami.Icon {
                source: Qt.resolvedUrl("../../icons/deepseek-symbolic.svg")
                isMask: true
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            QQC2.CheckBox {
                id: deepSeekToggle
                Layout.fillWidth: true
                text: "API 账户余额"
            }
        }

        Kirigami.Heading {
            Kirigami.FormData.isSection: true
            text: "刷新设置"
        }

        QQC2.SpinBox {
            id: refreshInterval
            Kirigami.FormData.label: "自动刷新间隔"
            from: 1
            to: 240
            editable: true
            value: 5
            textFromValue: function(value) {
                return value + " 分钟"
            }
            valueFromText: function(text, locale) {
                const match = text.match(/\d+/)
                const parsed = match ? Number(match[0]) : 5
                return Math.max(1, Math.min(240, parsed))
            }
        }
    }
}
