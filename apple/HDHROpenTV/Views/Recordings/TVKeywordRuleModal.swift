import SwiftUI
import HDHROpenKit

// tvOS counterpart to iOSKeywordRuleSheet.swift — creates a standalone
// standing rule with no backing airing. Always ends up on the builtin DVR
// (enforced server-side too, see RecordingsViewModel.createKeywordRule), so
// unlike TVRecordingOptionsModal there's no server picker here.
public struct TVKeywordRuleModal: View {
    let onCreated: () -> Void

    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @Environment(\.dismiss) private var dismiss

    @Namespace private var focusNamespace

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
                    Text("Add Keyword Rule")
                        .font(.title.bold())
                        .foregroundColor(Theme.textPrimary)

                    Spacer()

                    Button("Cancel") { dismiss() }
                }

                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        VStack(alignment: .leading, spacing: 10) {
                            sectionLabel("Title")
                            TextField("Title", text: $title)
                                .padding(12)
                                .background(Theme.appSurfaceVariant)
                                .cornerRadius(10)
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
                        }

                        if !guideViewModel.channels.isEmpty {
                            VStack(alignment: .leading, spacing: 10) {
                                sectionLabel("Channel")
                                choiceRow(
                                    [("Any channel", "any"), ("Select channels…", "custom")],
                                    selection: $channelMode
                                )

                                if channelMode == "custom" {
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
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            sectionLabel("Padding")
                            stepperRow("Start", value: $startPaddingMinutes, range: 0...60)
                            stepperRow("End", value: $endPaddingMinutes, range: 0...60)
                        }

                        Toggle("New episodes only", isOn: $recentOnly)

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
                    }
                    .padding(.trailing, 12)
                }

                HStack {
                    Button {
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
                    } label: {
                        Label("Create", systemImage: "plus.circle")
                            .padding(.horizontal, 20)
                            .padding(.vertical, 12)
                    }
                    .disabled(!canSubmit)
                    .prefersDefaultFocus(true, in: focusNamespace)

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
