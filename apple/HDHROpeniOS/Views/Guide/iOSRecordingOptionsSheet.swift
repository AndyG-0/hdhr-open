import SwiftUI
import HDHROpenKit

// Mirrors the web client's HDHomeRunRecordingOptionsDialog.svelte: keyword
// query or "contains" title matching forces the rule onto the builtin DVR
// server (enforced again server-side by dvr.py), and per-episode retention
// is meaningless (and hidden) once the rule targets the official HDHomeRun
// RECORD engine, which manages its own retention.
public struct iOSRecordingOptionsSheet: View {
    let channel: HDHomeRunChannel
    let airing: HDHomeRunGuideEntry
    let canRecordSeries: Bool
    let existingRule: HDHomeRunRecordingRule?
    let onConfirm: (Bool, RecordingRuleOptions) -> Void
    let onCancelRule: (() -> Void)?

    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @Environment(\.dismiss) private var dismiss

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

    public var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(airing.title).font(.headline)
                }

                Section(header: Text("DVR Server")) {
                    Picker("Server", selection: $server) {
                        Text("Default").tag("default")
                        Text("Built-in DVR").tag("builtin")
                        Text("HDHomeRun RECORD").tag("hdhomerun")
                    }
                }

                Section(header: Text("Title Match")) {
                    Picker("Match", selection: $titleMatchMode) {
                        Text("Exact title").tag("exact")
                        Text("Title contains").tag("contains")
                    }
                    .pickerStyle(.segmented)
                }

                Section {
                    TextField("Keywords (optional)", text: $keywordQuery)
                    if let epTitle = airing.episodeTitle, !epTitle.isEmpty,
                       !keywordQuery.lowercased().contains(epTitle.lowercased()) {
                        Button("+ Use \"\(epTitle)\" as keyword") {
                            let trimmed = keywordQuery.trimmingCharacters(in: .whitespaces)
                            keywordQuery = trimmed.isEmpty ? epTitle : "\(trimmed), \(epTitle)"
                        }
                    }
                } footer: {
                    if isKeywordActive {
                        Text("Keyword and contains-match rules always record via the built-in DVR.")
                    }
                }

                Section(header: Text("Channel")) {
                    Picker("Channel", selection: $channelMode) {
                        Text("Channel \(channel.channelNumber)").tag("current")
                        Text("Any channel").tag("any")
                        if !guideViewModel.channels.isEmpty {
                            Text("Select channels…").tag("custom")
                        }
                    }
                    .pickerStyle(.segmented)
                }

                if channelMode == "custom" && !guideViewModel.channels.isEmpty {
                    Section(header: Text("Channels")) {
                        ForEach(guideViewModel.channels) { ch in
                            Button {
                                if customChannels.contains(ch.channelNumber) {
                                    customChannels.remove(ch.channelNumber)
                                } else {
                                    customChannels.insert(ch.channelNumber)
                                }
                            } label: {
                                HStack {
                                    Text("\(ch.channelNumber) \(ch.name)")
                                        .foregroundColor(.primary)
                                    Spacer()
                                    if customChannels.contains(ch.channelNumber) {
                                        Image(systemName: "checkmark")
                                            .foregroundColor(.blue)
                                    }
                                }
                            }
                        }
                    }
                }

                Section(header: Text("Padding")) {
                    Stepper("Start: \(startPaddingMinutes) min", value: $startPaddingMinutes, in: 0...60)
                    Stepper("End: \(endPaddingMinutes) min", value: $endPaddingMinutes, in: 0...60)
                }

                Section {
                    Toggle("New episodes only", isOn: $recentOnly)
                }

                Section(footer: isOfficialDvrTarget ? Text("Retention is managed by the official HDHomeRun DVR.") : nil) {
                    if !isOfficialDvrTarget {
                        Picker("Keep episodes", selection: $retentionMode) {
                            Text("Unlimited").tag("unlimited")
                            Text("Keep last N").tag("limited")
                        }
                        .pickerStyle(.segmented)
                        if retentionMode == "limited" {
                            TextField("Episodes to keep", text: $retentionCount)
                                .keyboardType(.numberPad)
                        }
                    }
                }

                Section {
                    if let rule = existingRule, let onCancelRule {
                        Button(role: .destructive) {
                            onCancelRule()
                            dismiss()
                        } label: {
                            Text("Cancel Recording").frame(maxWidth: .infinity)
                        }
                        .id(rule.recordingRuleId)
                    } else {
                        Button {
                            onConfirm(false, buildOptions())
                            dismiss()
                        } label: {
                            Text("Record Episode").frame(maxWidth: .infinity)
                        }
                        if canRecordSeries {
                            Button {
                                onConfirm(true, buildOptions())
                                dismiss()
                            } label: {
                                Text(isKeywordActive ? "Record Series (with keywords)" : "Record Series")
                                    .frame(maxWidth: .infinity)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Recording Options")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}
