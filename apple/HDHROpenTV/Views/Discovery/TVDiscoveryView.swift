import HDHROpenKit
import SwiftUI

/// tvOS counterpart to `iOSDiscoveryView.swift`: a grid of recommendations
/// from `GET /api/discovery`, with the same "New & Notable" fallback banner
/// when `hasProfile == false`, and recording wired through the existing
/// `TVRecordingOptionsModal` (Discovery candidates never already have a
/// recording rule, so `existingRule` is always nil).
public struct TVDiscoveryView: View {
    @EnvironmentObject private var discoveryViewModel: DiscoveryViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel

    @State private var selectedAiring: HDHomeRunGuideEntry?

    @FocusState private var focusedFilter: DiscoveryBucketFilter?

    public init() {}

    private let columns = [
        GridItem(.adaptive(minimum: 220, maximum: 260), spacing: 28)
    ]

    /// Discovery items only carry a `channelNumber` string, but
    /// `TVRecordingOptionsModal` wants a full `HDHomeRunChannel` - look it
    /// up from the guide's already-loaded channel list, same as the
    /// program-detail modal does, falling back to a bare channel if the
    /// guide hasn't loaded that channel for some reason.
    private func channel(for airing: HDHomeRunGuideEntry) -> HDHomeRunChannel {
        let number = airing.channelNumber ?? ""
        return guideViewModel.channels.first { $0.channelNumber == number }
            ?? HDHomeRunChannel(channelNumber: number, name: number)
    }

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 20) {
                HStack(alignment: .center, spacing: 20) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Discovery")
                            .font(.largeTitle.bold())
                            .foregroundColor(Theme.textPrimary)

                        if !discoveryViewModel.hasProfile, !discoveryViewModel.items.isEmpty {
                            Text("New & Notable — record a few shows to get picks tailored to you.")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    }

                    Spacer()

                    // Bucket filter: a focusable pill row rather than a
                    // `.segmented` Picker (tvOS renders those poorly). Local
                    // filter of the single fetch above - switching buckets
                    // never triggers a second network call.
                    HStack(spacing: 12) {
                        ForEach(DiscoveryBucketFilter.allCases, id: \.self) { bucketFilter in
                            let isFocused = focusedFilter == bucketFilter
                            let isSelected = discoveryViewModel.filter == bucketFilter

                            Button(action: {
                                discoveryViewModel.filter = bucketFilter
                            }) {
                                Text(bucketFilter.label)
                                    .font(.callout.bold())
                                    .foregroundColor(isSelected ? .white : .secondary)
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 8)
                                    .background(isSelected ? Color.blue : Theme.appSurfaceVariant)
                                    .cornerRadius(20)
                                    .overlay(
                                        Capsule()
                                            .stroke(isFocused ? Theme.textPrimary : Color.clear, lineWidth: 3)
                                    )
                                    .scaleEffect(isFocused ? 1.08 : 1.0)
                                    .animation(.easeInOut(duration: 0.15), value: isFocused)
                            }
                            .buttonStyle(.plain)
                            .focused($focusedFilter, equals: bucketFilter)
                        }
                    }
                }
                .padding(.horizontal, 48)
                .padding(.top, 24)

                if discoveryViewModel.isLoading, discoveryViewModel.items.isEmpty {
                    VStack {
                        Spacer()
                        ProgressView("Loading Discovery...")
                            .scaleEffect(1.5)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else if discoveryViewModel.filteredItems.isEmpty {
                    VStack(spacing: 16) {
                        Spacer()
                        Image(systemName: "sparkles")
                            .font(.system(size: 64))
                            .foregroundColor(.secondary)
                        Text("No recommendations right now. Check back after the guide updates.")
                            .font(.title2)
                            .foregroundColor(.secondary)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else {
                    ScrollView {
                        LazyVGrid(columns: columns, spacing: 32) {
                            ForEach(discoveryViewModel.filteredItems) { airing in
                                TVDiscoveryCardView(airing: airing) {
                                    selectedAiring = airing
                                }
                            }
                        }
                        .padding(.horizontal, 48)
                        .padding(.bottom, 64)
                    }
                }
            }
        }
        .task {
            if discoveryViewModel.items.isEmpty {
                await discoveryViewModel.loadData()
            }
        }
        .fullScreenCover(item: $selectedAiring) { airing in
            TVRecordingOptionsModal(
                channel: channel(for: airing),
                airing: airing,
                canRecordSeries: true,
                existingRule: nil,
                onConfirm: { recordSeries, options in
                    let targetChannel = channel(for: airing)
                    selectedAiring = nil
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
