import SwiftUI
import HDHROpenKit

private struct SelectedAiring: Identifiable {
    let channel: HDHomeRunChannel
    let airing: HDHomeRunGuideEntry

    var id: String { "\(channel.channelNumber)_\(airing.id)" }
}

public struct TVGuideView: View {
    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel

    @State private var selectedAiringForModal: SelectedAiring?

    public init() {}

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 16) {
                // Header & Filter Bar
                HStack(alignment: .center) {
                    Text("Live TV Guide")
                        .font(.largeTitle.bold())
                        .foregroundColor(Theme.textPrimary)

                    Spacer()

                    Button(action: {
                        guideViewModel.filterOnlyFavorites.toggle()
                    }) {
                        HStack(spacing: 8) {
                            Image(systemName: guideViewModel.filterOnlyFavorites ? "star.fill" : "star")
                                .foregroundColor(.yellow)
                            Text("Favorites Only")
                        }
                    }

                    Button(action: {
                        Task { await guideViewModel.loadData() }
                    }) {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                }
                .padding(.horizontal, 48)
                .padding(.top, 24)

                // EPG Guide Grid List
                if guideViewModel.isLoading && guideViewModel.channels.isEmpty {
                    VStack {
                        Spacer()
                        ProgressView("Loading Guide...")
                            .scaleEffect(1.5)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else if guideViewModel.displayedChannels.isEmpty {
                    VStack(spacing: 16) {
                        Spacer()
                        Image(systemName: "tv.slash")
                            .font(.system(size: 64))
                            .foregroundColor(.secondary)
                        Text(guideViewModel.filterOnlyFavorites ? "No favorite channels" : "No channels discovered")
                            .font(.title2)
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else {
                    ScrollView(.vertical, showsIndicators: false) {
                        LazyVStack(spacing: 20) {
                            ForEach(guideViewModel.displayedChannels) { channel in
                                let airings = guideViewModel.getAirings(for: channel.channelNumber)
                                let isFav = guideViewModel.favoriteChannels.contains(channel.channelNumber)

                                TVChannelRowView(
                                    channel: channel,
                                    airings: airings,
                                    isFavorite: isFav,
                                    onSelectAiring: { airing in
                                        selectedAiringForModal = SelectedAiring(channel: channel, airing: airing)
                                    },
                                    onTuneChannel: {
                                        Task {
                                            await playerViewModel.playChannel(channel: channel)
                                        }
                                    },
                                    onToggleFavorite: {
                                        Task {
                                            await guideViewModel.toggleFavorite(channelNumber: channel.channelNumber)
                                        }
                                    }
                                )
                            }
                        }
                        .padding(.horizontal, 48)
                        .padding(.bottom, 64)
                    }
                }
            }
        }
        .fullScreenCover(item: $selectedAiringForModal) { selection in
            let rule = guideViewModel.findRule(for: selection.channel.channelNumber, airing: selection.airing)
            let isFav = guideViewModel.favoriteChannels.contains(selection.channel.channelNumber)

            TVProgramDetailModal(
                channel: selection.channel,
                airing: selection.airing,
                existingRule: rule,
                isFavorite: isFav,
                onWatch: {
                    selectedAiringForModal = nil
                    Task {
                        await playerViewModel.playChannel(channel: selection.channel, airing: selection.airing)
                    }
                },
                onRecordEpisode: {
                    selectedAiringForModal = nil
                    Task {
                        try? await guideViewModel.recordEpisode(
                            seriesId: selection.airing.seriesId,
                            channelNumber: selection.channel.channelNumber,
                            start: selection.airing.start
                        )
                    }
                },
                onRecordSeries: {
                    guard let seriesId = selection.airing.seriesId else { return }
                    selectedAiringForModal = nil
                    Task {
                        try? await guideViewModel.recordSeries(
                            seriesId: seriesId,
                            channelNumber: selection.channel.channelNumber
                        )
                    }
                },
                onCancelRule: { ruleId in
                    selectedAiringForModal = nil
                    Task {
                        try? await guideViewModel.cancelRule(ruleId: ruleId)
                    }
                },
                onToggleFavorite: {
                    Task {
                        await guideViewModel.toggleFavorite(channelNumber: selection.channel.channelNumber)
                    }
                },
                onDismiss: {
                    selectedAiringForModal = nil
                }
            )
        }
        .task {
            if guideViewModel.channels.isEmpty {
                await guideViewModel.loadData()
            }
        }
    }
}
