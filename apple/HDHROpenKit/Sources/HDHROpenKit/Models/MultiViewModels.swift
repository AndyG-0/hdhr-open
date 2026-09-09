import Foundation

/// Grid presentation layout for multi-feed playback.
public enum MultiViewLayout: String, CaseIterable, Codable, Sendable, Identifiable {
    /// 2 feeds displayed side-by-side (50/50 split).
    case sideBySide = "side_by_side"
    /// 3 feeds displayed as 1 primary hero tile and 2 stacked side tiles.
    case threeBox = "three_box"
    /// 4 feeds displayed in a 2x2 quad box.
    case quad

    public var id: String {
        rawValue
    }

    /// Maximum number of streams this layout accommodates.
    public var maxSlots: Int {
        switch self {
        case .sideBySide:
            2
        case .threeBox:
            3
        case .quad:
            4
        }
    }

    /// User-facing display title for layout picker menus.
    public var displayName: String {
        switch self {
        case .sideBySide:
            "Side by Side (2)"
        case .threeBox:
            "Three-Box (3)"
        case .quad:
            "Quad Grid (4)"
        }
    }

    /// Returns layouts available for a given maximum feed limit (based on physical tuner capacity).
    public static func availableLayouts(for maxFeeds: Int) -> [MultiViewLayout] {
        if maxFeeds <= 2 {
            [.sideBySide]
        } else if maxFeeds == 3 {
            [.sideBySide, .threeBox]
        } else {
            [.sideBySide, .threeBox, .quad]
        }
    }

    /// Returns the ideal layout recommendation for the given number of active feeds and max capacity.
    public static func recommended(for slotCount: Int, maxFeeds: Int = 4) -> MultiViewLayout {
        let allowed = availableLayouts(for: maxFeeds)
        if slotCount <= 2 || !allowed.contains(.threeBox) {
            return .sideBySide
        } else if slotCount == 3 || !allowed.contains(.quad) {
            return .threeBox
        } else {
            return .quad
        }
    }
}

/// Result of evaluating real-time tuner capacity and sharing availability.
public struct TunerAvailabilityResult: Sendable, Equatable {
    public let available: Bool
    public let isShared: Bool
    public let totalTuners: Int
    public let activeRecordingsCount: Int
    public let activeStreamsCount: Int
    public let sharableChannels: [String]
    public let explanation: String?

    public init(
        available: Bool,
        isShared: Bool,
        totalTuners: Int,
        activeRecordingsCount: Int,
        activeStreamsCount: Int,
        sharableChannels: [String],
        explanation: String? = nil
    ) {
        self.available = available
        self.isShared = isShared
        self.totalTuners = totalTuners
        self.activeRecordingsCount = activeRecordingsCount
        self.activeStreamsCount = activeStreamsCount
        self.sharableChannels = sharableChannels
        self.explanation = explanation
    }
}

/// Represents an individual video feed tile within a multi-view session.
public struct MultiViewSlot: Identifiable, Equatable {
    public let id: UUID
    public var channel: HDHomeRunChannel
    public var airing: HDHomeRunGuideEntry?
    public let playerEngine: PlayerEngine
    public var watchRecording: HDHomeRunRecording?
    public var hlsSessionId: String?
    public var isMuted: Bool
    public var warningMessage: String?
    public var playbackMode: PlaybackMode?
    /// Bumped by `MultiPlayerViewModel` at the start of every negotiation
    /// (`finishAddFeed`/`replaceFeed`) targeting this slot, so a negotiation
    /// that resumes after the slot was removed or re-targeted can detect it's
    /// stale and tear down the session it just negotiated instead of
    /// silently leaking it or clobbering a newer negotiation's result. Not
    /// part of the slot's user-visible identity, so it's excluded from `==`.
    public var negotiationGeneration: Int

    public init(
        id: UUID = UUID(),
        channel: HDHomeRunChannel,
        airing: HDHomeRunGuideEntry? = nil,
        playerEngine: PlayerEngine,
        watchRecording: HDHomeRunRecording? = nil,
        hlsSessionId: String? = nil,
        isMuted: Bool = true,
        warningMessage: String? = nil,
        playbackMode: PlaybackMode? = .serverTranscodedHls,
        negotiationGeneration: Int = 0
    ) {
        self.id = id
        self.channel = channel
        self.airing = airing
        self.playerEngine = playerEngine
        self.watchRecording = watchRecording
        self.hlsSessionId = hlsSessionId
        self.isMuted = isMuted
        self.warningMessage = warningMessage
        self.playbackMode = playbackMode
        self.negotiationGeneration = negotiationGeneration
    }

    @MainActor
    public static func makeSlot(
        id: UUID = UUID(),
        channel: HDHomeRunChannel,
        airing: HDHomeRunGuideEntry? = nil,
        isMuted: Bool = true,
        warningMessage: String? = nil,
        playbackMode: PlaybackMode? = .serverTranscodedHls
    ) -> MultiViewSlot {
        MultiViewSlot(
            id: id,
            channel: channel,
            airing: airing,
            playerEngine: PlayerEngine(),
            isMuted: isMuted,
            warningMessage: warningMessage,
            playbackMode: playbackMode
        )
    }

    public var title: String {
        airing?.title ?? channel.name
    }

    public var subtitle: String? {
        airing?.episodeTitle ?? channel.channelNumber
    }

    public var channelNumber: String {
        channel.channelNumber
    }

    public var channelName: String {
        channel.name
    }

    public nonisolated static func == (lhs: MultiViewSlot, rhs: MultiViewSlot) -> Bool {
        lhs.id == rhs.id &&
            lhs.channel == rhs.channel &&
            lhs.airing == rhs.airing &&
            lhs.watchRecording?.recordingId == rhs.watchRecording?.recordingId &&
            lhs.hlsSessionId == rhs.hlsSessionId &&
            lhs.isMuted == rhs.isMuted &&
            lhs.warningMessage == rhs.warningMessage &&
            lhs.playbackMode == rhs.playbackMode
    }
}

/// Errors specific to multi-view playback orchestration.
public enum MultiViewError: LocalizedError, Sendable, Equatable {
    case maxSlotsReached
    case slotNotFound(Int)
    case streamURLCreationFailed
    case tunerUnavailable(String)

    public var errorDescription: String? {
        switch self {
        case .maxSlotsReached:
            "Maximum of 4 concurrent feeds reached."
        case let .slotNotFound(index):
            "No multi-view slot found at index \(index)."
        case .streamURLCreationFailed:
            "Could not construct playable stream URL."
        case let .tunerUnavailable(message):
            message
        }
    }
}
