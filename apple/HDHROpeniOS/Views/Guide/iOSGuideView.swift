import HDHROpenKit
import SwiftUI

public struct iOSGuideView: View {
    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel

    @State private var searchText = ""
    @State private var selectedAiringForSheet: (channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry)?
    @State private var showAIAssistantSheet = false

    public init() {}

    private var filteredChannels: [HDHomeRunChannel] {
        let base = guideViewModel.displayedChannels
        if searchText.isEmpty {
            return base
        }
        return base.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) ||
                $0.channelNumber.contains(searchText) ||
                ($0.now?.title.localizedCaseInsensitiveContains(searchText) == true)
        }
    }

    public var body: some View {
        iOSGuideGridView(
            channels: filteredChannels,
            onSelectAiring: { channel, airing in
                selectedAiringForSheet = (channel, airing)
            },
            onTuneChannel: { channel in
                Task { await playerViewModel.playChannel(channel: channel) }
            }
        )
        .searchable(text: $searchText, prompt: "Search channels or shows")
        .navigationTitle("Live Guide")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Toggle(isOn: $guideViewModel.filterOnlyFavorites) {
                    Image(systemName: guideViewModel.filterOnlyFavorites ? "star.fill" : "star")
                        .foregroundColor(guideViewModel.filterOnlyFavorites ? .yellow : .primary)
                }
            }

            ToolbarItem(placement: .topBarTrailing) {
                Button(action: {
                    showAIAssistantSheet = true
                }) {
                    Image(systemName: "sparkles")
                }
                .accessibilityLabel("AI Assistant")
            }

            ToolbarItem(placement: .topBarTrailing) {
                Button(action: {
                    Task { await guideViewModel.loadData() }
                }) {
                    Image(systemName: "arrow.clockwise")
                }
            }
        }
        .sheet(item: Binding(
            get: { selectedAiringForSheet.map { AiringWrapper(channel: $0.channel, airing: $0.airing) } },
            set: { _ in selectedAiringForSheet = nil }
        )) { wrapper in
            iOSProgramDetailSheet(channel: wrapper.channel, airing: wrapper.airing)
        }
        .sheet(isPresented: $showAIAssistantSheet) {
            iOSAIAssistantSheet(apiClient: guideViewModel.apiClient)
        }
        .refreshable {
            await guideViewModel.loadData()
        }
        .task {
            await guideViewModel.loadData()
        }
    }
}

private struct AiringWrapper: Identifiable {
    var id: String {
        "\(channel.channelNumber)_\(airing.id)"
    }

    let channel: HDHomeRunChannel
    let airing: HDHomeRunGuideEntry
}
