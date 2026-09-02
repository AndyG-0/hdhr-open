import SwiftUI
import HDHROpenKit

// tvOS counterpart to iOSRecordingOptionsSheet.swift — same business rules
// (keyword/contains-match forces the builtin DVR; retention is hidden once
// the rule targets the official HDHomeRun DVR, which manages its own
// retention), adapted for D-pad focus navigation: segmented choices become
// button groups (tvOS's Picker doesn't render a usable segmented style),
// and there's no navigation bar, so Cancel/Close live in an explicit header
// like the rest of this app's tvOS modals. Keyword text entry uses a plain
// TextField and tvOS's on-screen remote keyboard, the same precedent
// TVServerConnectionFields.swift already relies on for the server URL field.
public struct TVRecordingOptionsModal: View {
    let channel: HDHomeRunChannel
    let airing: HDHomeRunGuideEntry
    let canRecordSeries: Bool
    let existingRule: HDHomeRunRecordingRule?
    let onConfirm: (Bool, RecordingRuleOptions) -> Void
    let onCancelRule: (() -> Void)?

    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @Environment(\.dismiss) private var dismiss

    @Namespace private var focusNamespace

    @State private var server = "default"
    @State private var titleMatchMode = "exact"
    @State private var keywordQuery = ""
    @State private var channelMode = "current"
    @State private var customChannels: Set<String>
    @State private var startPaddingMinutes = 0
    @State private var endPaddingMinutes = 0
    @State private var recentOnly = false
    @State private var retentionMode = "unlimited"
    @State private var retentionCount = "3"

    public init(
        channel: HDHomeRunChannel,
        airing: HDHomeRunGuideEntry,
        canRecordSeries: Bool,
        existingRule: HDHomeRunRecordingRule?,
        onConfirm: @escaping (Bool, RecordingRuleOptions) -> Void,
        onCancelRule: (() -> Void)?
    ) {
        self.channel = channel
        self.airing = airing
        self.canRecordSeries = canRecordSeries
        self.existingRule = existingRule
        self.onConfirm = onConfirm
        self.onCancelRule = onCancelRule
        _customChannels = State(initialValue: [channel.channelNumber])
    }

    private var officialDvrActive: Bool {
        recordingsViewModel.dvrInfo?.isBuiltin == false
    }

    private var isKeywordActive: Bool {
        !keywordQuery.trimmingCharacters(in: .whitespaces).isEmpty || titleMatchMode == "contains"
    }

    private var isOfficialDvrTarget: Bool {
        !isKeywordActive && (server == "hdhomerun" || (server == "default" && officialDvrActive))
    }

    private func effectiveChannel() -> String? {
        switch channelMode {
        case "any":
            return nil
        case "custom":
            let filtered = customChannels.filter { !$0.isEmpty }
            return filtered.isEmpty ? nil : filtered.sorted().joined(separator: "|")
        default:
            return channel.channelNumber
        }
    }

    private func buildOptions() -> RecordingRuleOptions {
        let trimmedKeyword = keywordQuery.trimmingCharacters(in: .whitespaces)
        let hasKeywords = !trimmedKeyword.isEmpty
        let hasContains = titleMatchMode == "contains"
        let serverToUse: String? = (hasKeywords || hasContains) ? "builtin" : (server != "default" ? server : nil)
        return RecordingRuleOptions(
            title: airing.title,
            titleMatchMode: hasContains ? "contains" : "exact",
            keywordQuery: hasKeywords ? trimmedKeyword : nil,
            channel: effectiveChannel(),
            startPadding: startPaddingMinutes != 0 ? startPaddingMinutes * 60 : nil,
            endPadding: endPaddingMinutes != 0 ? endPaddingMinutes * 60 : nil,
            recentOnly: recentOnly ? true : nil,
            maxEpisodesToKeep: (!isOfficialDvrTarget && retentionMode == "limited")
                ? Int(retentionCount).flatMap { $0 > 0 ? $0 : nil }
                : nil,
            server: serverToUse
        )
    }

    private func choiceRow(_ options: [(label: String, tag: String)], selection: Binding<String>) -> some View {
        HStack(spacing: 12) {
            ForEach(options, id: \.tag) { option in
                let isActive = selection.wrappedValue == option.tag
                Button(action: { selection.wrappedValue = option.tag }) {
                    Text(option.label)
                        .font(.callout.bold())
                        .foregroundColor(isActive ? .white : Theme.textPrimary)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 10)
                        .background(isActive ? Color.blue : Theme.appSurfaceVariant)
                        .cornerRadius(10)
                }
                .buttonStyle(.card)
            }
        }
    }

    private func sectionLabel(_ text: String) -> some View {
        Text(text)
            .font(.headline)
            .foregroundColor(.secondary)
    }

    // Stepper is unavailable on tvOS, so padding uses a hand-rolled +/- row.
    private func stepperRow(_ label: String, value: Binding<Int>, range: ClosedRange<Int>) -> some View {
        HStack {
            Text("\(label): \(value.wrappedValue) min")
            Spacer()
            HStack(spacing: 16) {
                Button(action: { value.wrappedValue = max(range.lowerBound, value.wrappedValue - 5) }) {
                    Image(systemName: "minus.circle")
                }
                .buttonStyle(.card)

                Button(action: { value.wrappedValue = min(range.upperBound, value.wrappedValue + 5) }) {
                    Image(systemName: "plus.circle")
                }
                .buttonStyle(.card)
            }
        }
    }

    public var body: some View {
        ZStack {
            Color.black.opacity(0.85).ignoresSafeArea()

            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Recording Options")
                            .font(.title.bold())
                            .foregroundColor(Theme.textPrimary)
                        Text(airing.title)
                            .font(.headline)
                            .foregroundColor(.secondary)
                    }

                    Spacer()

                    Button("Cancel") { dismiss() }
                }

                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        VStack(alignment: .leading, spacing: 10) {
                            sectionLabel("DVR Server")
                            choiceRow(
                                [("Default", "default"), ("Built-in DVR", "builtin"), ("HDHomeRun RECORD", "hdhomerun")],
                                selection: $server
                            )
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            sectionLabel("Title Match")
                            choiceRow(
                                [("Exact title", "exact"), ("Title contains", "contains")],
                                selection: $titleMatchMode
                            )
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            sectionLabel("Keywords")
                            TextField("Keywords (optional)", text: $keywordQuery)
                                .padding(12)
                                .background(Theme.appSurfaceVariant)
                                .cornerRadius(10)
                            if let epTitle = airing.episodeTitle, !epTitle.isEmpty,
                               !keywordQuery.lowercased().contains(epTitle.lowercased()) {
                                Button("+ Use \"\(epTitle)\" as keyword") {
                                    let trimmed = keywordQuery.trimmingCharacters(in: .whitespaces)
                                    keywordQuery = trimmed.isEmpty ? epTitle : "\(trimmed), \(epTitle)"
                                }
                            }
                            if isKeywordActive {
                                Text("Keyword and contains-match rules always record via the built-in DVR.")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            sectionLabel("Channel")
                            var channelOptions: [(label: String, tag: String)] {
                                var opts: [(label: String, tag: String)] = [
                                    ("Channel \(channel.channelNumber)", "current"),
                                    ("Any channel", "any")
                                ]
                                if !guideViewModel.channels.isEmpty {
                                    opts.append(("Select channels…", "custom"))
                                }
                                return opts
                            }
                            choiceRow(channelOptions, selection: $channelMode)

                            if channelMode == "custom" && !guideViewModel.channels.isEmpty {
                                LazyVStack(alignment: .leading, spacing: 8) {
                                    ForEach(guideViewModel.channels) { ch in
                                        let isSelected = customChannels.contains(ch.channelNumber)
                                        Button(action: {
                                            if isSelected {
                                                customChannels.remove(ch.channelNumber)
                                            } else {
                                                customChannels.insert(ch.channelNumber)
                                            }
                                        }) {
                                            HStack {
                                                Text("\(ch.channelNumber)  \(ch.name)")
                                                Spacer()
                                                if isSelected {
                                                    Image(systemName: "checkmark")
                                                        .foregroundColor(.blue)
                                                }
                                            }
                                            .padding(.horizontal, 16)
                                            .padding(.vertical, 8)
                                            .background(Theme.appSurfaceVariant)
                                            .cornerRadius(8)
                                        }
                                        .buttonStyle(.card)
                                    }
                                }
                                .frame(maxHeight: 220)
                            }
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            sectionLabel("Padding")
                            stepperRow("Start", value: $startPaddingMinutes, range: 0...60)
                            stepperRow("End", value: $endPaddingMinutes, range: 0...60)
                        }

                        Toggle("New episodes only", isOn: $recentOnly)

                        if !isOfficialDvrTarget {
                            VStack(alignment: .leading, spacing: 10) {
                                sectionLabel("Keep Episodes")
                                choiceRow(
                                    [("Unlimited", "unlimited"), ("Keep last N", "limited")],
                                    selection: $retentionMode
                                )
                                if retentionMode == "limited" {
                                    TextField("Episodes to keep", text: $retentionCount)
                                        .padding(12)
                                        .background(Theme.appSurfaceVariant)
                                        .cornerRadius(10)
                                }
                            }
                        } else {
                            Text("Retention is managed by the official HDHomeRun DVR.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(.trailing, 12)
                }

                HStack(spacing: 20) {
                    if let rule = existingRule, let onCancelRule {
                        Button(role: .destructive) {
                            onCancelRule()
                        } label: {
                            Label("Cancel Recording", systemImage: "record.circle")
                                .padding(.horizontal, 20)
                                .padding(.vertical, 12)
                        }
                        .id(rule.recordingRuleId)
                        .prefersDefaultFocus(true, in: focusNamespace)
                    } else {
                        Button {
                            onConfirm(false, buildOptions())
                            dismiss()
                        } label: {
                            Label("Record Episode", systemImage: "record.circle")
                                .padding(.horizontal, 20)
                                .padding(.vertical, 12)
                        }
                        .prefersDefaultFocus(true, in: focusNamespace)

                        if canRecordSeries {
                            Button {
                                onConfirm(true, buildOptions())
                                dismiss()
                            } label: {
                                Label(isKeywordActive ? "Record Series (with keywords)" : "Record Series", systemImage: "recordingtape")
                                    .padding(.horizontal, 20)
                                    .padding(.vertical, 12)
                            }
                        }
                    }

                    Spacer()
                }
            }
            .padding(48)
            .frame(maxWidth: 1200, maxHeight: 900)
            .background(Theme.appSurface)
            .cornerRadius(24)
            .overlay(
                RoundedRectangle(cornerRadius: 24)
                    .stroke(Theme.appBorder, lineWidth: 1)
            )
        }
        .focusScope(focusNamespace)
    }
}
