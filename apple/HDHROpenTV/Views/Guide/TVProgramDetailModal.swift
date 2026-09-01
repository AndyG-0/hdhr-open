import SwiftUI
import HDHROpenKit

public struct TVProgramDetailModal: View {
    let channel: HDHomeRunChannel
    let airing: HDHomeRunGuideEntry
    let existingRule: HDHomeRunRecordingRule?
    let isFavorite: Bool

    let onWatch: () -> Void
    let onRecordEpisode: () -> Void
    let onRecordSeries: () -> Void
    let onCancelRule: (String) -> Void
    let onToggleFavorite: () -> Void
    let onDismiss: () -> Void

    @Namespace private var focusNamespace

    public init(
        channel: HDHomeRunChannel,
        airing: HDHomeRunGuideEntry,
        existingRule: HDHomeRunRecordingRule?,
        isFavorite: Bool,
        onWatch: @escaping () -> Void,
        onRecordEpisode: @escaping () -> Void,
        onRecordSeries: @escaping () -> Void,
        onCancelRule: @escaping (String) -> Void,
        onToggleFavorite: @escaping () -> Void,
        onDismiss: @escaping () -> Void
    ) {
        self.channel = channel
        self.airing = airing
        self.existingRule = existingRule
        self.isFavorite = isFavorite
        self.onWatch = onWatch
        self.onRecordEpisode = onRecordEpisode
        self.onRecordSeries = onRecordSeries
        self.onCancelRule = onCancelRule
        self.onToggleFavorite = onToggleFavorite
        self.onDismiss = onDismiss
    }

    public var body: some View {
        ZStack {
            Color.black.opacity(0.85).ignoresSafeArea()

            VStack(alignment: .leading, spacing: 24) {
                // Header
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 12) {
                            Text(channel.channelNumber)
                                .font(.title3.bold())
                                .foregroundColor(.blue)

                            Text(channel.name)
                                .font(.title3)
                                .foregroundColor(.secondary)

                            if isFavorite {
                                Image(systemName: "star.fill")
                                    .foregroundColor(.yellow)
                            }

                            if channel.isHD {
                                Text("HD")
                                    .font(.caption.bold())
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.blue)
                                    .foregroundColor(.white)
                                    .cornerRadius(4)
                            }
                        }

                        Text(airing.title)
                            .font(.system(size: 38, weight: .bold))
                            .foregroundColor(Theme.textPrimary)

                        if let epDesig = airing.formattedEpisodeDesignation {
                            if let ep = airing.episodeTitle, !ep.isEmpty {
                                Text("\(epDesig) • \(ep)")
                                    .font(.title2)
                                    .foregroundColor(Theme.textSecondary)
                            } else {
                                Text(epDesig)
                                    .font(.title2)
                                    .foregroundColor(Theme.textSecondary)
                            }
                        } else if let ep = airing.episodeTitle, !ep.isEmpty {
                            Text(ep)
                                .font(.title2)
                                .foregroundColor(Theme.textSecondary)
                        }

                        HStack(spacing: 12) {
                            if airing.hasCC != false {
                                Text("CC")
                                    .font(.caption.bold())
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.secondary.opacity(0.3))
                                    .foregroundColor(Theme.textPrimary)
                                    .cornerRadius(4)
                            }

                            if airing.isNew == true {
                                Text("NEW")
                                    .font(.caption.bold())
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.green.opacity(0.3))
                                    .foregroundColor(.green)
                                    .cornerRadius(4)
                            }

                            if let audio = airing.formattedAudio, !audio.isEmpty {
                                Text(audio)
                                    .font(.caption.bold())
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.secondary.opacity(0.3))
                                    .foregroundColor(Theme.textPrimary)
                                    .cornerRadius(4)
                            }

                            if let cat = airing.category, !cat.isEmpty {
                                Text(cat)
                                    .font(.caption)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(Color.secondary.opacity(0.2))
                                    .foregroundColor(Theme.textSecondary)
                                    .cornerRadius(4)
                            }
                        }

                        HStack(spacing: 16) {
                            Text(TimeFormatting.formatTimeRange(start: airing.start, end: airing.end))
                                .font(.headline)
                                .foregroundColor(Theme.textSecondary)

                            if let airDate = airing.originalAirdate, !airDate.isEmpty {
                                Text("Original Air Date: \(airDate)")
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }

                    Spacer()

                    if let img = airing.imageUrl, let url = URL(string: img) {
                        AsyncImage(url: url) { image in
                            image.resizable().aspectRatio(contentMode: .fill)
                        } placeholder: {
                            Theme.appSurfaceVariant
                        }
                        .frame(width: 220, height: 130)
                        .cornerRadius(12)
                    }
                }

                // Synopsis
                if let syn = airing.synopsis, !syn.isEmpty {
                    Text(syn)
                        .font(.body)
                        .foregroundColor(Theme.textPrimary)
                        .lineLimit(4)
                }

                Spacer()

                // Actions Bar
                HStack(spacing: 20) {
                    if airing.isCurrentlyAiring() {
                        Button(action: onWatch) {
                            Label("Watch Live", systemImage: "play.fill")
                                .padding(.horizontal, 20)
                                .padding(.vertical, 12)
                        }
                        .prefersDefaultFocus(true, in: focusNamespace)
                    }

                    if let rule = existingRule {
                        Button(role: .destructive, action: { onCancelRule(rule.recordingRuleId) }) {
                            Label("Cancel Recording", systemImage: "record.circle")
                                .padding(.horizontal, 20)
                                .padding(.vertical, 12)
                        }
                        .prefersDefaultFocus(!airing.isCurrentlyAiring(), in: focusNamespace)
                    } else {
                        Button(action: onRecordEpisode) {
                            Label("Record Episode", systemImage: "record.circle")
                                .padding(.horizontal, 20)
                                .padding(.vertical, 12)
                        }
                        .prefersDefaultFocus(!airing.isCurrentlyAiring(), in: focusNamespace)

                        if let seriesId = airing.seriesId, !seriesId.isEmpty {
                            Button(action: onRecordSeries) {
                                Label("Record Series", systemImage: "recordingtape")
                                    .padding(.horizontal, 20)
                                    .padding(.vertical, 12)
                            }
                        }
                    }

                    Button(action: onToggleFavorite) {
                        Label(isFavorite ? "Unfavorite Channel" : "Favorite Channel", systemImage: isFavorite ? "star.slash" : "star")
                            .padding(.horizontal, 16)
                            .padding(.vertical, 12)
                    }

                    Spacer()

                    Button(action: onDismiss) {
                        Text("Close")
                            .padding(.horizontal, 24)
                            .padding(.vertical, 12)
                    }
                }
            }
            .padding(48)
            .frame(maxWidth: 1200, maxHeight: 600)
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
