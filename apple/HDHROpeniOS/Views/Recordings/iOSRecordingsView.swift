import SwiftUI
import HDHROpenKit

public struct iOSRecordingsView: View {
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel

    @State private var selectedRecordingForSheet: HDHomeRunRecording?
    @State private var showRulesSheet = false

    public init() {}

    public var body: some View {
        List {
            // Free Space Header Section
            if let info = recordingsViewModel.dvrInfo {
                Section {
                    HStack {
                        Label(info.friendlyName, systemImage: "internaldrive")
                            .font(.subheadline)
                        Spacer()
                        Text(info.formattedFreeSpace)
                            .font(.subheadline.bold())
                            .foregroundColor(.blue)
                    }
                }
            }

            // Category Picker
            Section {
                Picker("Category", selection: $recordingsViewModel.selectedFilter) {
                    ForEach(RecordingCategoryFilter.allCases) { cat in
                        Text(cat.rawValue).tag(cat)
                    }
                }
                .pickerStyle(.segmented)
            }

            // Recordings List
            Section(header: Text("\(recordingsViewModel.filteredRecordings.count) Recordings")) {
                if recordingsViewModel.filteredRecordings.isEmpty {
                    Text("No recordings available")
                        .foregroundColor(.secondary)
                } else {
                    ForEach(recordingsViewModel.filteredRecordings) { recording in
                        HStack(alignment: .top, spacing: 12) {
                            Button(action: {
                                selectedRecordingForSheet = recording
                            }) {
                                HStack(alignment: .top, spacing: 12) {
                                    // Thumbnail
                                    ZStack(alignment: .bottomLeading) {
                                        if let img = recording.imageUrl, let url = URL(string: img) {
                                            AsyncImage(url: url) { image in
                                                image.resizable().aspectRatio(16/9, contentMode: .fill)
                                            } placeholder: {
                                                Color.gray.opacity(0.2)
                                            }
                                        } else {
                                            Color.gray.opacity(0.15)
                                        }

                                        if recording.isInProgress {
                                            Text("REC")
                                                .font(.system(size: 8, weight: .bold))
                                                .padding(3)
                                                .background(Color.red)
                                                .foregroundColor(.white)
                                                .cornerRadius(2)
                                                .padding(4)
                                        }
                                    }
                                    .frame(width: 90, height: 50)
                                    .cornerRadius(6)
                                    .clipped()

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(recording.title)
                                            .font(.headline)
                                            .foregroundColor(.primary)
                                            .lineLimit(1)

                                        if let ep = recording.episodeTitle {
                                            Text(ep)
                                                .font(.caption)
                                                .foregroundColor(.secondary)
                                                .lineLimit(1)
                                        }

                                        HStack {
                                            if let des = recording.episodeDesignation {
                                                Text(des)
                                                    .font(.caption2.bold())
                                                    .foregroundColor(.blue)
                                            }
                                            if !recording.formattedDuration.isEmpty {
                                                Text(recording.formattedDuration)
                                                    .font(.caption2)
                                                    .foregroundColor(.secondary)
                                            }
                                            Text(recording.isHDHomeRunNative ? "HDHomeRun DVR" : "Built-in")
                                                .font(.caption2)
                                                .foregroundColor(.secondary)
                                        }
                                    }
                                }
                            }
                            .buttonStyle(.plain)

                            Spacer()

                            Button(action: {
                                Task { await playerViewModel.playRecording(recording) }
                            }) {
                                Image(systemName: "play.circle.fill")
                                    .font(.title2)
                                    .foregroundColor(.blue)
                            }
                            .buttonStyle(.borderless)
                        }
                        .swipeActions(edge: .trailing) {
                            if !recording.isInProgress && !recording.isHDHomeRunNative {
                                Button(role: .destructive) {
                                    Task { try? await recordingsViewModel.deleteRecording(recording) }
                                } label: {
                                    Label("Delete", systemImage: "trash")
                                }
                            }
                        }
                    }
                }
            }
        }
        .refreshable {
            await recordingsViewModel.loadData()
        }
        .navigationTitle("DVR Library")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(action: {
                    showRulesSheet = true
                }) {
                    Image(systemName: "list.bullet.rectangle")
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                Button(action: {
                    Task { await recordingsViewModel.loadData() }
                }) {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
        .sheet(item: $selectedRecordingForSheet) { recording in
            iOSRecordingDetailSheet(recording: recording)
        }
        .sheet(isPresented: $showRulesSheet) {
            iOSRecordingRulesSheet()
        }
        .task {
            if recordingsViewModel.recordings.isEmpty {
                await recordingsViewModel.loadData()
            }
        }
    }
}
