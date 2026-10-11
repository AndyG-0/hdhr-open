import HDHROpenKit
import SwiftUI

/// Recommendations pulled from `GET /api/discovery`: upcoming guide airings
/// scored from the household's recording history, or a "New & Notable"
/// fallback when there's no history yet (`hasProfile == false`). Recording
/// reuses `iOSRecordingOptionsSheet` unchanged - the same sheet the Guide's
/// program-detail view presents - since the backend guarantees a Discovery
/// candidate never already has a recording rule (`existingRule` is always
/// nil here).
public struct iOSDiscoveryView: View {
    @EnvironmentObject private var discoveryViewModel: DiscoveryViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel

    @State private var selectedAiring: HDHomeRunGuideEntry?

    public init() {}

    /// Discovery items only carry a `channelNumber` string, but
    /// `iOSRecordingOptionsSheet` wants a full `HDHomeRunChannel` (name,
    /// HD flag, etc.) - look it up from the guide's already-loaded channel
    /// list, same as the program-detail sheet does, falling back to a bare
    /// channel if the guide hasn't loaded that channel for some reason.
    private func channel(for airing: HDHomeRunGuideEntry) -> HDHomeRunChannel {
        let number = airing.channelNumber ?? ""
        return guideViewModel.channels.first { $0.channelNumber == number }
            ?? HDHomeRunChannel(channelNumber: number, name: number)
    }

    /// Mirrors the web/Android `discovery.*` source labels - shown on every
    /// non-"personalized" item so users can see why something was recommended.
    private func sourceBadgeLabel(_ source: String?) -> String? {
        switch source {
        case "active_rule": "Active rule"
        case "favorite_team": "Favorite team"
        case "network_pick": "Network pick"
        case "new_and_notable": "New & notable"
        default: nil
        }
    }

    public var body: some View {
        List {
            if !discoveryViewModel.hasProfile, !discoveryViewModel.items.isEmpty {
                Section {
                    Text("New & Notable — record a few shows to get picks tailored to you.")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
            }

            Section {
                // Bucket filter: a local filter of the single fetch above -
                // switching buckets never triggers a second network call.
                Picker("Filter", selection: $discoveryViewModel.filter) {
                    ForEach(DiscoveryBucketFilter.allCases, id: \.self) { bucketFilter in
                        Text(bucketFilter.label).tag(bucketFilter)
                    }
                }
                .pickerStyle(.segmented)
                .listRowInsets(EdgeInsets())
                .padding(.vertical, 4)
            }

            Section {
                if discoveryViewModel.filteredItems.isEmpty {
                    Text(discoveryViewModel.isLoading ? "Loading…" : "No recommendations right now. Check back after the guide updates.")
                        .foregroundColor(.secondary)
                } else {
                    ForEach(discoveryViewModel.filteredItems) { airing in
                        Button {
                            selectedAiring = airing
                        } label: {
                            HStack(alignment: .top, spacing: 12) {
                                ZStack {
                                    if let img = airing.imageUrl, let url = URL(string: img) {
                                        AsyncImage(url: url) { image in
                                            image.resizable().aspectRatio(2 / 3, contentMode: .fill)
                                        } placeholder: {
                                            Color.gray.opacity(0.2)
                                        }
                                    } else {
                                        Color.gray.opacity(0.15)
                                    }
                                }
                                .frame(width: 60, height: 90)
                                .cornerRadius(6)
                                .clipped()

                                VStack(alignment: .leading, spacing: 2) {
                                    Text(airing.title)
                                        .font(.headline)
                                        .foregroundColor(.primary)
                                        .lineLimit(1)

                                    if let ep = airing.episodeTitle, !ep.isEmpty {
                                        Text(ep)
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                            .lineLimit(1)
                                    }

                                    HStack(spacing: 6) {
                                        if airing.isNew == true {
                                            Text("NEW")
                                                .font(.caption2.bold())
                                                .padding(.horizontal, 4)
                                                .padding(.vertical, 1)
                                                .background(Color.green.opacity(0.2))
                                                .foregroundColor(.green)
                                                .cornerRadius(3)
                                        }
                                        if let channelNumber = airing.channelNumber {
                                            Text(channelNumber)
                                                .font(.caption2.bold())
                                                .foregroundColor(.blue)
                                        }
                                    }

                                    Text(
                                        "\(TimeFormatting.formatDayDate(airing.start)) • "
                                            + "\(TimeFormatting.formatTimeRange(start: airing.start, end: airing.end))"
                                    )
                                    .font(.caption2)
                                    .foregroundColor(.secondary)

                                    if let cat = airing.category, !cat.isEmpty {
                                        Text(cat.components(separatedBy: ",").first?.trimmingCharacters(in: .whitespaces) ?? cat)
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }

                                    if let badgeLabel = sourceBadgeLabel(airing.source) {
                                        Text(badgeLabel)
                                            .font(.caption2)
                                            .padding(.horizontal, 4)
                                            .padding(.vertical, 1)
                                            .background(Color.secondary.opacity(0.15))
                                            .foregroundColor(.secondary)
                                            .cornerRadius(3)
                                    }
                                }
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .refreshable {
            await discoveryViewModel.loadData()
        }
        .navigationTitle("Discovery")
        .task {
            if discoveryViewModel.items.isEmpty {
                await discoveryViewModel.loadData()
            }
        }
        .sheet(item: $selectedAiring) { airing in
            iOSRecordingOptionsSheet(
                channel: channel(for: airing),
                airing: airing,
                canRecordSeries: true,
                existingRule: nil,
                onConfirm: { recordSeries, options in
                    let targetChannel = channel(for: airing)
                    Task {
                        if recordSeries {
                            try? await guideViewModel.recordSeries(
                                seriesId: airing.seriesId ?? "",
                                channelNumber: targetChannel.channelNumber,
                                options: options
                            )
                        } else {
                            try? await guideViewModel.recordEpisode(
                                seriesId: airing.seriesId,
                                channelNumber: targetChannel.channelNumber,
                                start: airing.start,
                                options: options
                            )
                        }
                    }
                },
                onCancelRule: nil
            )
        }
    }
}
