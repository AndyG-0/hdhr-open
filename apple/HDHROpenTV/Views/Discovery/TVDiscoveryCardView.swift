import HDHROpenKit
import SwiftUI

/// tvOS counterpart to `TVRecordingCardView.swift`: same poster-card shape
/// and D-pad focus treatment, applied to a recommended `HDHomeRunGuideEntry`
/// instead of a `HDHomeRunRecording`.
public struct TVDiscoveryCardView: View {
    let airing: HDHomeRunGuideEntry
    let onSelect: () -> Void

    @FocusState private var isFocused: Bool

    public init(airing: HDHomeRunGuideEntry, onSelect: @escaping () -> Void) {
        self.airing = airing
        self.onSelect = onSelect
    }

    /// Mirrors the web/Android/iOS `discovery.*` source labels - shown on
    /// every non-"personalized" item so users can see why something was
    /// recommended.
    private var sourceBadgeLabel: String? {
        switch airing.source {
        case "active_rule": "Active rule"
        case "favorite_team": "Favorite team"
        case "network_pick": "Network pick"
        case "new_and_notable": "New & notable"
        default: nil
        }
    }

    public var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: 6) {
                // Poster Image / Placeholder
                ZStack(alignment: .topTrailing) {
                    if let img = airing.imageUrl, let url = URL(string: img) {
                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .aspectRatio(2 / 3, contentMode: .fill)
                        } placeholder: {
                            Theme.appSurfaceVariant
                        }
                    } else {
                        ZStack {
                            Theme.appSurface
                            Image(systemName: "sparkles")
                                .font(.system(size: 40))
                                .foregroundColor(Theme.textMuted)
                        }
                    }

                    if airing.isNew == true {
                        Text("NEW")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.green.opacity(0.85))
                            .cornerRadius(4)
                            .padding(8)
                    }
                }
                .frame(width: 220, height: 330)
                .cornerRadius(10)
                .clipped()

                // Metadata
                VStack(alignment: .leading, spacing: 2) {
                    Text(airing.title)
                        .font(.headline)
                        .foregroundColor(Theme.textPrimary)
                        .lineLimit(1)

                    if let ep = airing.episodeTitle, !ep.isEmpty {
                        Text(ep)
                            .font(.subheadline)
                            .foregroundColor(Theme.textSecondary)
                            .lineLimit(1)
                    }

                    if let badgeLabel = sourceBadgeLabel {
                        Text(badgeLabel)
                            .font(.caption2.bold())
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Theme.appSurfaceVariant)
                            .foregroundColor(Theme.textSecondary)
                            .cornerRadius(4)
                    }

                    HStack {
                        if let channelNumber = airing.channelNumber {
                            Text(channelNumber)
                                .font(.caption.bold())
                                .foregroundColor(.blue)
                        }

                        Spacer()

                        Text(TimeFormatting.formatDayDate(airing.start))
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal, 4)
            }
            .frame(width: 220)
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
