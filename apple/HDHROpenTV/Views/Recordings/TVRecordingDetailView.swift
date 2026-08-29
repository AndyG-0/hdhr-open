import SwiftUI
import HDHROpenKit

public struct TVRecordingDetailView: View {
    let recording: HDHomeRunRecording
    let onPlay: () -> Void
    let onDelete: () -> Void
    let onDismiss: () -> Void

    @Namespace private var focusNamespace

    public init(
        recording: HDHomeRunRecording,
        onPlay: @escaping () -> Void,
        onDelete: @escaping () -> Void,
        onDismiss: @escaping () -> Void
    ) {
        self.recording = recording
        self.onPlay = onPlay
        self.onDelete = onDelete
        self.onDismiss = onDismiss
    }

    public var body: some View {
        ZStack {
            Color.black.opacity(0.85).ignoresSafeArea()

            VStack(alignment: .leading, spacing: 24) {
                HStack(alignment: .top, spacing: 32) {
                    if let img = recording.imageUrl, let url = URL(string: img) {
                        AsyncImage(url: url) { image in
                            image.resizable().aspectRatio(contentMode: .fill)
                        } placeholder: {
                            Color.gray.opacity(0.2)
                        }
                        .frame(width: 360, height: 200)
                        .cornerRadius(12)
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text(recording.title)
                            .font(.system(size: 38, weight: .bold))
                            .foregroundColor(.white)

                        if let ep = recording.episodeTitle, !ep.isEmpty {
                            Text(ep)
                                .font(.title2)
                                .foregroundColor(.gray)
                        }

                        HStack(spacing: 16) {
                            if let des = recording.episodeDesignation {
                                Text(des)
                                    .font(.headline)
                                    .foregroundColor(.blue)
                            }
                            if let ch = recording.channelName {
                                Text(ch)
                                    .font(.headline)
                                    .foregroundColor(.secondary)
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
                        }
                    }
                }

                if let syn = recording.synopsis, !syn.isEmpty {
                    Text(syn)
                        .font(.body)
                        .foregroundColor(.white.opacity(0.9))
                        .lineLimit(4)
                }

                Spacer()

                HStack(spacing: 24) {
                    Button(action: onPlay) {
                        Label(recording.isInProgress ? "Watch In-Progress" : "Play Recording", systemImage: "play.fill")
                            .padding(.horizontal, 24)
                            .padding(.vertical, 12)
                    }
                    .prefersDefaultFocus(true, in: focusNamespace)

                    if !recording.isInProgress {
                        Button(role: .destructive, action: onDelete) {
                            Label("Delete Recording", systemImage: "trash")
                                .padding(.horizontal, 20)
                                .padding(.vertical, 12)
                        }
                    }

                    Spacer()

                    Button("Close", action: onDismiss)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 12)
                }
            }
            .padding(48)
            .frame(maxWidth: 1100, maxHeight: 560)
            .background(Color(white: 0.12))
            .cornerRadius(24)
        }
        .focusScope(focusNamespace)
    }
}
