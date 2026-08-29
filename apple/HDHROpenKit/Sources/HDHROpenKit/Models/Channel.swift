import Foundation

public struct HDHomeRunChannel: Identifiable, Codable, Sendable, Hashable {
    public var id: String { channelNumber }
    public let channelNumber: String
    public let name: String
    public let isHD: Bool
    public let isDRM: Bool
    public let streamUrl: String
    public let playbackUrl: String?
    public let now: HDHomeRunGuideEntry?
    public let next: HDHomeRunGuideEntry?

    enum CodingKeys: String, CodingKey {
        case channelNumber = "channel_number"
        case name
        case isHD = "is_hd"
        case isDRM = "is_drm"
        case streamUrl = "stream_url"
        case playbackUrl = "playback_url"
        case now
        case next
    }

    public init(
        channelNumber: String,
        name: String,
        isHD: Bool = false,
        isDRM: Bool = false,
        streamUrl: String = "",
        playbackUrl: String? = nil,
        now: HDHomeRunGuideEntry? = nil,
        next: HDHomeRunGuideEntry? = nil
    ) {
        self.channelNumber = channelNumber
        self.name = name
        self.isHD = isHD
        self.isDRM = isDRM
        self.streamUrl = streamUrl
        self.playbackUrl = playbackUrl
        self.now = now
        self.next = next
    }

    public var displayNumber: String {
        channelNumber
    }
}

public struct HDHomeRunChannelsResponse: Codable, Sendable {
    public let channels: [HDHomeRunChannel]
    public let guideAvailable: Bool

    enum CodingKeys: String, CodingKey {
        case channels
        case guideAvailable = "guide_available"
    }

    public init(channels: [HDHomeRunChannel], guideAvailable: Bool) {
        self.channels = channels
        self.guideAvailable = guideAvailable
    }
}

public struct HDHomeRunFullGuideChannel: Identifiable, Codable, Sendable, Hashable {
    public var id: String { channelNumber }
    public let channelNumber: String
    public let channelName: String
    public let airings: [HDHomeRunGuideEntry]

    enum CodingKeys: String, CodingKey {
        case channelNumber = "channel_number"
        case channelName = "channel_name"
        case airings
    }

    public init(channelNumber: String, channelName: String, airings: [HDHomeRunGuideEntry]) {
        self.channelNumber = channelNumber
        self.channelName = channelName
        self.airings = airings
    }
}

public struct HDHomeRunChannelSetting: Identifiable, Codable, Sendable {
    public let id: String
    public let channelNumber: String
    public let name: String
    public let isHD: Bool
    public let isFavorite: Bool
    public let hidden: Bool
    public let guideProvider: String?
    public let xmltvChannelId: String?
    public let xmltvDisplayName: String?
    public let sdStationId: String?
    public let sdLineupId: String?

    enum CodingKeys: String, CodingKey {
        case id
        case channelNumber = "channel_number"
        case name
        case isHD = "is_hd"
        case isFavorite = "is_favorite"
        case hidden
        case guideProvider = "guide_provider"
        case xmltvChannelId = "xmltv_channel_id"
        case xmltvDisplayName = "xmltv_display_name"
        case sdStationId = "sd_station_id"
        case sdLineupId = "sd_lineup_id"
    }
}
