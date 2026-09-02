import SwiftUI
import HDHROpenKit

public struct TVRecordingRulesView: View {
    let rules: [HDHomeRunRecordingRule]
    let onDeleteRule: (String) -> Void
    let onDismiss: () -> Void

    @Namespace private var focusNamespace
    @State private var showKeywordRuleModal = false

    public init(
        rules: [HDHomeRunRecordingRule],
        onDeleteRule: @escaping (String) -> Void,
        onDismiss: @escaping () -> Void
    ) {
        self.rules = rules
        self.onDeleteRule = onDeleteRule
        self.onDismiss = onDismiss
    }

    // Mirrors iOSRecordingRulesSheet.swift's badge set (itself mirroring
    // Android's RecordingRulesDialog.kt).
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

    public var body: some View {
        ZStack {
            Color.black.opacity(0.85).ignoresSafeArea()

            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    Text("Scheduled Recording Rules")
                        .font(.title.bold())
                        .foregroundColor(Theme.textPrimary)

                    Spacer()

                    Button(action: { showKeywordRuleModal = true }) {
                        Label("Add Keyword Rule", systemImage: "plus")
                    }

                    Button("Close", action: onDismiss)
                        .prefersDefaultFocus(true, in: focusNamespace)
                }

                if rules.isEmpty {
                    VStack(spacing: 12) {
                        Spacer()
                        Image(systemName: "calendar.badge.clock")
                            .font(.system(size: 56))
                            .foregroundColor(Theme.textMuted)
                        Text("No active recording rules scheduled")
                            .font(.title3)
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(rules) { rule in
                                HStack {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(rule.title)
                                            .font(.headline)
                                            .foregroundColor(Theme.textPrimary)

                                        HStack(spacing: 12) {
                                            Text(rule.isSeriesRule ? "Series Rule" : "Single Episode")
                                                .font(.caption.bold())
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(rule.isSeriesRule ? Color.purple.opacity(0.6) : Color.blue.opacity(0.6))
                                                .cornerRadius(4)

                                            if let ch = rule.channelOnly {
                                                Text("Channel \(ch)")
                                                    .font(.caption)
                                                    .foregroundColor(.secondary)
                                            }
                                        }

                                        let ruleBadges = badges(for: rule)
                                        if !ruleBadges.isEmpty {
                                            HStack(spacing: 6) {
                                                ForEach(ruleBadges, id: \.self) { badge in
                                                    Text(badge)
                                                        .font(.caption2)
                                                        .padding(.horizontal, 6)
                                                        .padding(.vertical, 2)
                                                        .background(Color.secondary.opacity(0.2))
                                                        .foregroundColor(Theme.textSecondary)
                                                        .cornerRadius(4)
                                                }
                                            }
                                        }
                                    }

                                    Spacer()

                                    Button(role: .destructive, action: {
                                        onDeleteRule(rule.recordingRuleId)
                                    }) {
                                        Label("Delete", systemImage: "trash")
                                    }
                                }
                                .padding(16)
                                .background(Theme.appSurfaceVariant)
                                .cornerRadius(12)
                            }
                        }
                    }
                }
            }
            .padding(48)
            .frame(maxWidth: 1000, maxHeight: 600)
            .background(Theme.appSurface)
            .cornerRadius(24)
        }
        .focusScope(focusNamespace)
        .fullScreenCover(isPresented: $showKeywordRuleModal) {
            TVKeywordRuleModal(onCreated: {})
        }
    }
}
