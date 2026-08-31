import SwiftUI
import HDHROpenKit

public struct TVRecordingsView: View {
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel

    @State private var selectedRecording: HDHomeRunRecording?
    @State private var showRulesModal: Bool = false

    @FocusState private var focusedFilter: RecordingCategoryFilter?
    @FocusState private var isRulesFocused: Bool
    @FocusState private var isRefreshFocused: Bool

    public init() {}

    private let columns = [
        GridItem(.adaptive(minimum: 280, maximum: 320), spacing: 28)
    ]

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 20) {
                // Header & Filter Bar
                HStack(alignment: .center, spacing: 20) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("DVR Library")
                            .font(.largeTitle.bold())
                            .foregroundColor(Theme.textPrimary)

                        if let info = recordingsViewModel.dvrInfo {
                            Text(info.formattedFreeSpace)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }

                    Spacer()

                    // Category Filter Pills
                    HStack(spacing: 12) {
                        ForEach(RecordingCategoryFilter.allCases) { cat in
                            let isFocused = focusedFilter == cat

                            Button(action: {
                                recordingsViewModel.selectedFilter = cat
                            }) {
                                Text(cat.rawValue)
                                    .font(.callout.bold())
                                    .foregroundColor(recordingsViewModel.selectedFilter == cat ? .white : .secondary)
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 8)
                                    .background(recordingsViewModel.selectedFilter == cat ? Color.blue : Theme.appSurfaceVariant)
                                    .cornerRadius(20)
                                    .overlay(
                                        Capsule()
                                            .stroke(isFocused ? Theme.textPrimary : Color.clear, lineWidth: 3)
                                    )
                                    .scaleEffect(isFocused ? 1.08 : 1.0)
                                    .animation(.easeInOut(duration: 0.15), value: isFocused)
                            }
                            .buttonStyle(.plain)
                            .focused($focusedFilter, equals: cat)
                        }
                    }

                    Button(action: { showRulesModal = true }) {
                        Label("Rules (\(recordingsViewModel.recordingRules.count))", systemImage: "calendar.badge.clock")
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(Theme.appSurfaceVariant)
                            .cornerRadius(20)
                            .overlay(
                                Capsule()
                                    .stroke(isRulesFocused ? Theme.textPrimary : Color.clear, lineWidth: 3)
                            )
                            .scaleEffect(isRulesFocused ? 1.08 : 1.0)
                            .animation(.easeInOut(duration: 0.15), value: isRulesFocused)
                    }
                    .buttonStyle(.plain)
                    .focused($isRulesFocused)

                    Button(action: {
                        Task { await recordingsViewModel.loadData() }
                    }) {
                        Image(systemName: "arrow.clockwise")
                            .frame(width: 44, height: 44)
                            .background(Theme.appSurfaceVariant)
                            .clipShape(Circle())
                            .overlay(
                                Circle()
                                    .stroke(isRefreshFocused ? Theme.textPrimary : Color.clear, lineWidth: 3)
                            )
                            .scaleEffect(isRefreshFocused ? 1.08 : 1.0)
                            .animation(.easeInOut(duration: 0.15), value: isRefreshFocused)
                    }
                    .buttonStyle(.plain)
                    .focused($isRefreshFocused)
                }
                .padding(.horizontal, 48)
                .padding(.top, 24)

                // Recordings Grid
                if recordingsViewModel.isLoading && recordingsViewModel.recordings.isEmpty {
                    VStack {
                        Spacer()
                        ProgressView("Loading Recordings...")
                            .scaleEffect(1.5)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else if recordingsViewModel.filteredRecordings.isEmpty {
                    VStack(spacing: 16) {
                        Spacer()
                        Image(systemName: "recordingtape")
                            .font(.system(size: 64))
                            .foregroundColor(.secondary)
                        Text("No recordings in this category")
                            .font(.title2)
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 32) {
                            ForEach(recordingsViewModel.filteredRecordings) { recording in
                                TVRecordingCardView(recording: recording) {
                                    selectedRecording = recording
                                }
                            }
                        }
                        .padding(.horizontal, 48)
                        .padding(.bottom, 64)
                    }
                }
            }
        }
        .fullScreenCover(item: $selectedRecording) { rec in
            TVRecordingDetailView(
                recording: rec,
                onPlay: {
                    selectedRecording = nil
                    Task {
                        await playerViewModel.playRecording(rec)
                    }
                },
                onDelete: {
                    selectedRecording = nil
                    Task {
                        try? await recordingsViewModel.deleteRecording(rec)
                    }
                },
                onDismiss: {
                    selectedRecording = nil
                }
            )
        }
        .fullScreenCover(isPresented: $showRulesModal) {
            TVRecordingRulesView(
                rules: recordingsViewModel.recordingRules,
                onDeleteRule: { ruleId in
                    Task {
                        try? await recordingsViewModel.deleteRule(ruleId: ruleId)
                    }
                },
                onDismiss: {
                    showRulesModal = false
                }
            )
        }
        .task {
            if recordingsViewModel.recordings.isEmpty {
                await recordingsViewModel.loadData()
            }
        }
    }
}
