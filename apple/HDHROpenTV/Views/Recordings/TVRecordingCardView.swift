import SwiftUI
import HDHROpenKit

public struct TVRecordingCardView: View {
    let recording: HDHomeRunRecording
    let onSelect: () -> Void

    @FocusState private var isFocused: Bool

    public init(recording: HDHomeRunRecording, onSelect: @escaping () -> Void) {
        self.recording = recording
        self.onSelect = onSelect
    }

    public var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: 6) {
                // Poster Image / Placeholder
                ZStack(alignment: .topTrailing) {
                    if let img = recording.imageUrl, let url = URL(string: img) {
                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .aspectRatio(16/9, contentMode: .fill)
                        } placeholder: {
                            Theme.appSurfaceVariant
                        }
                    } else {
                        ZStack {
                            Theme.appSurface
                            Image(systemName: "film")
                                .font(.system(size: 40))
                                .foregroundColor(Theme.textMuted)
                        }
                    }

                    if recording.isInProgress {
                        HStack(spacing: 4) {
                            Circle().fill(Color.red).frame(width: 8, height: 8)
                            Text("RECORDING")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(.white)
                        }
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.black.opacity(0.75))
                        .cornerRadius(4)
                        .padding(8)
                    }
                }
                .frame(width: 280, height: 160)
                .cornerRadius(10)
                .clipped()

                // Metadata
                VStack(alignment: .leading, spacing: 2) {
                    Text(recording.title)
                        .font(.headline)
                        .foregroundColor(Theme.textPrimary)
                        .lineLimit(1)

                    if let ep = recording.episodeTitle, !ep.isEmpty {
                        Text(ep)
                            .font(.subheadline)
                            .foregroundColor(Theme.textSecondary)
                            .lineLimit(1)
                    }

                    HStack {
                        if let des = recording.episodeDesignation {
                            Text(des)
                                .font(.caption.bold())
                                .foregroundColor(.blue)
                        }

                        if !recording.formattedDuration.isEmpty {
                            Text(recording.formattedDuration)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }

                        Spacer()

                        Text(recording.isHDHomeRunNative ? "HDHomeRun DVR" : "Built-in")
                            .font(.caption2)
                            .foregroundColor(.secondary)

                        if !recording.formattedFileSize.isEmpty {
                            Text(recording.formattedFileSize)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding(.horizontal, 4)
            }
            .frame(width: 280)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(isFocused ? Theme.textPrimary : Color.clear, lineWidth: 4)
            )
            .scaleEffect(isFocused ? 1.05 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: isFocused)
        }
        .buttonStyle(.plain)
        .focused($isFocused)
    }
}
