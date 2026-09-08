import Combine
import Foundation

@MainActor
public final class GuideViewModel: ObservableObject {
    @Published public private(set) var channels: [HDHomeRunChannel] = []
    @Published public private(set) var fullGuide: [HDHomeRunFullGuideChannel] = []
    @Published public private(set) var recordingRules: [HDHomeRunRecordingRule] = []
    @Published public private(set) var favoriteChannels: Set<String> = []
    @Published public var filterOnlyFavorites = false
    @Published public private(set) var isLoading = false
    @Published public private(set) var guideAvailable = false
    @Published public private(set) var error: String?

    public let apiClient: APIClient
    private let watchSessionManager: WatchSessionManager

    public init(apiClient: APIClient, watchSessionManager: WatchSessionManager) {
        self.apiClient = apiClient
        self.watchSessionManager = watchSessionManager
    }

    public var displayedChannels: [HDHomeRunChannel] {
        if filterOnlyFavorites, !favoriteChannels.isEmpty {
            return channels.filter { favoriteChannels.contains($0.channelNumber) }
        }
        return channels
    }

    public func loadData() async {
        guard !isLoading else { return }
        isLoading = true
        error = nil
        defer { isLoading = false }

        async let channelsTask = loadChannels()
        async let guideTask = loadGuide()
        async let favoritesTask = loadFavorites()
        async let rulesTask = loadRules()

        _ = await (channelsTask, guideTask, favoritesTask, rulesTask)
    }

    public func loadChannels() async {
        do {
            let resp = try await apiClient.getChannels()
            channels = resp.channels
            guideAvailable = resp.guideAvailable
        } catch {
            self.error = error.localizedDescription
            Log.general.error("Failed to load channels: \(error.localizedDescription)")
        }
    }

    public func loadGuide() async {
        do {
            let now = Date().timeIntervalSince1970
            let guide = try await apiClient.getGuide(start: now - 6 * 3600, end: now + 48 * 3600)
            fullGuide = guide
        } catch {
            Log.general.warning("Failed to load full guide: \(error.localizedDescription)")
        }
    }

    public func loadFavorites() async {
        do {
            let integration = try await apiClient.getNetworkIntegration(type: "hdhomerun")
            if let favs = integration.settings["favorite_channels"]?.value as? [String] {
                favoriteChannels = Set(favs)
            }
        } catch {
            // Favoriting is optional
        }
    }

    public func loadRules() async {
        do {
            recordingRules = try await apiClient.listRecordingRules()
        } catch {
            Log.dvr.warning("Failed to load recording rules: \(error.localizedDescription)")
        }
    }

    public func toggleFavorite(channelNumber: String) async {
        var updated = favoriteChannels
        if updated.contains(channelNumber) {
            updated.remove(channelNumber)
        } else {
            updated.insert(channelNumber)
        }
        favoriteChannels = updated

        // Persist to backend network integration settings
        do {
            let favsArray = Array(updated)
            _ = try await apiClient.updateNetworkIntegration(
                type: "hdhomerun",
                settings: ["favorite_channels": AnyCodable(favsArray)]
            )
        } catch {
            Log.general.error("Failed to save favorite channels: \(error.localizedDescription)")
        }
    }

    public func findRule(for channelNumber: String?, airing: HDHomeRunGuideEntry?) -> HDHomeRunRecordingRule? {
        RecordingRuleMatcher.findMatchingRule(rules: recordingRules, channelNumber: channelNumber, airing: airing)
    }

    public func recordEpisode(
        seriesId: String? = nil,
        channelNumber: String? = nil,
        start: TimeInterval? = nil,
        options: RecordingRuleOptions? = nil
    ) async throws {
        let payload = AddRecordingRulePayload(
            seriesId: (seriesId?.isEmpty ?? true) ? "auto" : seriesId!,
            dateTime: start,
            channel: options?.channel ?? channelNumber,
            title: options?.title,
            titleMatchMode: options?.titleMatchMode,
            keywordQuery: options?.keywordQuery,
            recentOnly: options?.recentOnly,
            startPadding: options?.startPadding,
            endPadding: options?.endPadding,
            maxEpisodesToKeep: options?.maxEpisodesToKeep,
            server: options?.server
        )
        recordingRules = try await apiClient.addRecordingRule(payload: payload)
        await loadRules()
    }

    public func recordSeries(
        seriesId: String,
        channelNumber: String? = nil,
        options: RecordingRuleOptions? = nil
    ) async throws {
        let payload = AddRecordingRulePayload(
            seriesId: seriesId.isEmpty ? "auto" : seriesId,
            channel: options?.channel ?? channelNumber,
            title: options?.title,
            titleMatchMode: options?.titleMatchMode,
            keywordQuery: options?.keywordQuery,
            recentOnly: options?.recentOnly ?? false,
            startPadding: options?.startPadding,
            endPadding: options?.endPadding,
            maxEpisodesToKeep: options?.maxEpisodesToKeep,
            server: options?.server
        )
        recordingRules = try await apiClient.addRecordingRule(payload: payload)
        await loadRules()
    }

    public func updateRule(
        ruleId: String,
        isSeries: Bool,
        options: RecordingRuleOptions? = nil,
        seriesId: String? = nil,
        start: TimeInterval? = nil,
        channelNumber: String? = nil
    ) async throws {
        let payload = AddRecordingRulePayload(
            seriesId: (seriesId?.isEmpty ?? true) ? "auto" : seriesId!,
            dateTime: isSeries ? nil : start,
            channel: options?.channel ?? channelNumber,
            title: options?.title,
            titleMatchMode: options?.titleMatchMode,
            keywordQuery: options?.keywordQuery,
            recentOnly: isSeries ? (options?.recentOnly ?? false) : nil,
            startPadding: options?.startPadding,
            endPadding: options?.endPadding,
            maxEpisodesToKeep: options?.maxEpisodesToKeep,
            server: options?.server
        )
        recordingRules = try await apiClient.updateRecordingRule(id: ruleId, payload: payload)
        await loadRules()
    }

    public func cancelRule(ruleId: String) async throws {
        recordingRules = try await apiClient.deleteRecordingRule(id: ruleId)
        await loadRules()
    }

    public func getAirings(for channelNumber: String) -> [HDHomeRunGuideEntry] {
        if let full = fullGuide.first(where: { $0.channelNumber == channelNumber }) {
            return full.airings
        }
        if let ch = channels.first(where: { $0.channelNumber == channelNumber }) {
            var items: [HDHomeRunGuideEntry] = []
            if let now = ch.now {
                items.append(now)
            }
            if let next = ch.next {
                items.append(next)
            }
            return items
        }
        return []
    }
}
