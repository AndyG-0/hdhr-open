import SwiftUI
import HDHROpenKit

// Mirrors the web client's HDHomeRunKeywordRuleDialog.svelte — creates a
// standalone standing rule with no backing airing. Always ends up on the
// builtin DVR (enforced server-side too, see RecordingsViewModel.createKeywordRule),
// so unlike iOSRecordingOptionsSheet there's no server picker here.
public struct iOSKeywordRuleSheet: View {
    let onCreated: () -> Void

    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var titleMatchMode = "exact"
    @State private var keywordQuery = ""
    @State private var channelMode = "any"
    @State private var customChannels: Set<String> = []
    @State private var startPaddingMinutes = 0
    @State private var endPaddingMinutes = 0
    @State private var recentOnly = false
    @State private var retentionMode = "unlimited"
    @State private var retentionCount = "3"
    @State private var isSaving = false

    public init(onCreated: @escaping () -> Void) {
        self.onCreated = onCreated
    }

    private var canSubmit: Bool {
        !title.trimmingCharacters(in: .whitespaces).isEmpty && !isSaving
    }

    private func effectiveChannel() -> String? {
        guard channelMode == "custom" else { return nil }
        let filtered = customChannels.filter { !$0.isEmpty }
        return filtered.isEmpty ? nil : filtered.sorted().joined(separator: "|")
    }

    private func buildOptions() -> RecordingRuleOptions {
        let trimmedKeyword = keywordQuery.trimmingCharacters(in: .whitespaces)
        return RecordingRuleOptions(
            titleMatchMode: titleMatchMode == "contains" ? "contains" : "exact",
            keywordQuery: trimmedKeyword.isEmpty ? nil : trimmedKeyword,
            channel: effectiveChannel(),
            startPadding: startPaddingMinutes != 0 ? startPaddingMinutes * 60 : nil,
            endPadding: endPaddingMinutes != 0 ? endPaddingMinutes * 60 : nil,
            recentOnly: recentOnly ? true : nil,
            maxEpisodesToKeep: retentionMode == "limited"
                ? Int(retentionCount).flatMap { $0 > 0 ? $0 : nil }
                : nil
        )
    }

    public var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Title", text: $title)
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
                }

                if !guideViewModel.channels.isEmpty {
                    Section(header: Text("Channel")) {
                        Picker("Channel", selection: $channelMode) {
                            Text("Any channel").tag("any")
                            Text("Select channels…").tag("custom")
                        }
                        .pickerStyle(.segmented)
                    }

                    if channelMode == "custom" {
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
                }

                Section(header: Text("Padding")) {
                    Stepper("Start: \(startPaddingMinutes) min", value: $startPaddingMinutes, in: 0...60)
                    Stepper("End: \(endPaddingMinutes) min", value: $endPaddingMinutes, in: 0...60)
                }

                Section {
                    Toggle("New episodes only", isOn: $recentOnly)
                }

                Section {
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
            .navigationTitle("Add Keyword Rule")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Create") {
                        let trimmedTitle = title.trimmingCharacters(in: .whitespaces)
                        let options = buildOptions()
                        isSaving = true
                        Task {
                            try? await recordingsViewModel.createKeywordRule(title: trimmedTitle, options: options)
                            await recordingsViewModel.loadRules()
                            isSaving = false
                            onCreated()
                            dismiss()
                        }
                    }
                    .disabled(!canSubmit)
                }
            }
        }
    }
}
