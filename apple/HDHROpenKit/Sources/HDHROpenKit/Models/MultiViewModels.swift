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

    /// Returns the ideal layout recommendation for the given number of active feeds.
    public static func recommended(for slotCount: Int) -> MultiViewLayout {
        switch slotCount {
        case ...2:
            .sideBySide
        case 3:
            .threeBox
        default:
            .quad
        }
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

    public init(
        id: UUID = UUID(),
        channel: HDHomeRunChannel,
        airing: HDHomeRunGuideEntry? = nil,
        playerEngine: PlayerEngine,
        watchRecording: HDHomeRunRecording? = nil,
        hlsSessionId: String? = nil,
        isMuted: Bool = true,
        warningMessage: String? = nil,
        playbackMode: PlaybackMode? = .serverTranscodedHls
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
