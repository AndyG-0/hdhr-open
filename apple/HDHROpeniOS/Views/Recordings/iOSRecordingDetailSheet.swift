import SwiftUI
import HDHROpenKit

public struct iOSRecordingDetailSheet: View {
    let recording: HDHomeRunRecording

    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @Environment(\.dismiss) private var dismiss

    public init(recording: HDHomeRunRecording) {
        self.recording = recording
    }

    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let img = recording.imageUrl, let url = URL(string: img) {
                        AsyncImage(url: url) { image in
                            image.resizable().aspectRatio(16/9, contentMode: .fill)
                        } placeholder: {
                            Color.gray.opacity(0.2)
                        }
                        .frame(maxWidth: .infinity, maxHeight: 220)
                        .cornerRadius(12)
                        .clipped()
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        Text(recording.title)
                            .font(.title2.bold())

                        if let ep = recording.episodeTitle {
                            Text(ep)
                                .font(.headline)
                                .foregroundColor(.secondary)
                        }

                        HStack(spacing: 12) {
                            if let des = recording.episodeDesignation {
                                Text(des)
                                    .font(.subheadline.bold())
                                    .foregroundColor(.blue)
                            }
                            if !recording.formattedDuration.isEmpty {
                                Text(recording.formattedDuration)
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                            if !recording.formattedFileSize.isEmpty {
                                Text(recording.formattedFileSize)
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                            Text(recording.isHDHomeRunNative ? "HDHomeRun DVR" : "Built-in")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    }

                    if let syn = recording.synopsis, !syn.isEmpty {
                        Text(syn)
                            .font(.body)
                    }

                    Divider().padding(.vertical, 8)

                    VStack(spacing: 12) {
                        Button(action: {
                            dismiss()
                            Task { await playerViewModel.playRecording(recording) }
                        }) {
                            Label(recording.isInProgress ? "Watch In-Progress" : "Play Recording", systemImage: "play.fill")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                        }
                        .buttonStyle(.borderedProminent)

                        if !recording.isHDHomeRunNative {
                            Button(role: .destructive, action: {
                                dismiss()
                                Task { try? await recordingsViewModel.deleteRecording(recording) }
                            }) {
                                Label("Delete Recording", systemImage: "trash")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 12)
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }
                .padding(20)
            }
            .navigationTitle("Recording Info")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
