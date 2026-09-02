import SwiftUI
import HDHROpenKit

// Mirrors the web client's rules-management list and Android's
// RecordingRulesDialog.kt badge set.
public struct iOSRecordingRulesSheet: View {
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var showKeywordRuleSheet = false

    public init() {}

    private func badges(for rule: HDHomeRunRecordingRule) -> [String] {
        var badges: [String] = []
        if let keyword = rule.keywordQuery, !keyword.isEmpty {
            badges.append("Keyword: \(keyword)")
        }
        if rule.titleMatchMode == "contains" {
            badges.append("Contains match")
        }
        if rule.recentOnly == 1 {
            badges.append("New only")
        }
        if let keep = rule.maxEpisodesToKeep {
            badges.append("Keep last \(keep)")
        }
        if let start = rule.startPadding, start != 0 {
            badges.append("Start +\(start / 60)m")
        }
        if let end = rule.endPadding, end != 0 {
            badges.append("End +\(end / 60)m")
        }
        if let provider = rule.provider {
            badges.append(provider)
        }
        return badges
    }

    private func deleteRules(at offsets: IndexSet) {
        let rules = recordingsViewModel.recordingRules
        let idsToDelete = offsets.map { rules[$0].recordingRuleId }
        Task {
            for id in idsToDelete {
                try? await recordingsViewModel.deleteRule(ruleId: id)
            }
            await recordingsViewModel.loadRules()
        }
    }

    public var body: some View {
        NavigationStack {
            List {
                if recordingsViewModel.recordingRules.isEmpty {
                    Text("No scheduled rules.")
                        .foregroundColor(.secondary)
                } else {
                    ForEach(recordingsViewModel.recordingRules) { rule in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(rule.title)
                                .font(.headline)

                            HStack(spacing: 4) {
                                Text(rule.isSeriesRule ? "Series Rule" : "Single Episode")
                                if let channel = rule.channelOnly {
                                    Text("• Ch \(channel)")
                                }
                            }
                            .font(.caption)
                            .foregroundColor(.secondary)

                            let ruleBadges = badges(for: rule)
                            if !ruleBadges.isEmpty {
                                ScrollView(.horizontal, showsIndicators: false) {
                                    HStack(spacing: 4) {
                                        ForEach(ruleBadges, id: \.self) { badge in
                                            Text(badge)
                                                .font(.caption2)
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(Color.secondary.opacity(0.15))
                                                .cornerRadius(4)
                                        }
                                    }
                                }
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    .onDelete(perform: deleteRules)
                }
            }
            .navigationTitle("Scheduled Rules")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Done") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showKeywordRuleSheet = true
                    } label: {
                        Label("Add Keyword Rule", systemImage: "plus")
                    }
                }
            }
            .task {
                if recordingsViewModel.recordingRules.isEmpty {
                    await recordingsViewModel.loadRules()
                }
            }
            .sheet(isPresented: $showKeywordRuleSheet) {
                iOSKeywordRuleSheet(onCreated: {})
            }
        }
    }
}
