import Foundation

public struct HDHomeRunRecordingRule: Identifiable, Codable, Sendable, Hashable {
    public var id: String { recordingRuleId }

    public let recordingRuleId: String
    public let seriesId: String
    public let title: String
    public let synopsis: String?
    public let imageUrl: String?
    public let channelOnly: String?
    public let dateTimeOnly: TimeInterval?
    public let priority: Int?
    public let startPadding: Int?
    public let endPadding: Int?
    public let recentOnly: Int?
    public let maxEpisodesToKeep: Int?
    public let titleMatchMode: String?
    public let keywordQuery: String?
    public let provider: String?

    enum CodingKeys: String, CodingKey {
        case recordingRuleId = "RecordingRuleID"
        case seriesId = "SeriesID"
        case title = "Title"
        case synopsis = "Synopsis"
        case imageUrl = "ImageURL"
        case channelOnly = "ChannelOnly"
        case dateTimeOnly = "DateTimeOnly"
        case priority = "Priority"
        case startPadding = "StartPadding"
        case endPadding = "EndPadding"
        case recentOnly = "RecentOnly"
        case maxEpisodesToKeep = "MaxEpisodesToKeep"
        case titleMatchMode = "TitleMatchMode"
        case keywordQuery = "KeywordQuery"
        case provider = "Provider"
    }

    public init(
        recordingRuleId: String,
        seriesId: String,
        title: String,
        synopsis: String? = nil,
        imageUrl: String? = nil,
        channelOnly: String? = nil,
        dateTimeOnly: TimeInterval? = nil,
        priority: Int? = nil,
        startPadding: Int? = nil,
        endPadding: Int? = nil,
        recentOnly: Int? = nil,
        maxEpisodesToKeep: Int? = nil,
        titleMatchMode: String? = nil,
        keywordQuery: String? = nil,
        provider: String? = nil
    ) {
        self.recordingRuleId = recordingRuleId
        self.seriesId = seriesId
        self.title = title
        self.synopsis = synopsis
        self.imageUrl = imageUrl
        self.channelOnly = channelOnly
        self.dateTimeOnly = dateTimeOnly
        self.priority = priority
        self.startPadding = startPadding
        self.endPadding = endPadding
        self.recentOnly = recentOnly
        self.maxEpisodesToKeep = maxEpisodesToKeep
        self.titleMatchMode = titleMatchMode
        self.keywordQuery = keywordQuery
        self.provider = provider
    }

    public var isSeriesRule: Bool {
        dateTimeOnly == nil
    }

    public var isEpisodeRule: Bool {
        dateTimeOnly != nil
    }
}

public struct RecordingRuleOptions: Sendable {
    public var title: String?
    public var titleMatchMode: String?
    public var keywordQuery: String?
    public var startPadding: Int?
    public var endPadding: Int?
    public var recentOnly: Bool?
    public var maxEpisodesToKeep: Int?
    public var server: String?

    public init(
        title: String? = nil,
        titleMatchMode: String? = nil,
        keywordQuery: String? = nil,
        startPadding: Int? = nil,
        endPadding: Int? = nil,
        recentOnly: Bool? = nil,
        maxEpisodesToKeep: Int? = nil,
        server: String? = nil
    ) {
        self.title = title
        self.titleMatchMode = titleMatchMode
        self.keywordQuery = keywordQuery
        self.startPadding = startPadding
        self.endPadding = endPadding
        self.recentOnly = recentOnly
        self.maxEpisodesToKeep = maxEpisodesToKeep
        self.server = server
    }
}

public struct AddRecordingRulePayload: Codable, Sendable {
    public let seriesId: String
    public let dateTime: TimeInterval?
    public let channel: String?
    public let title: String?
    public let titleMatchMode: String?
    public let keywordQuery: String?
    public let recentOnly: Bool?
    public let startPadding: Int?
    public let endPadding: Int?
    public let maxEpisodesToKeep: Int?
    public let server: String?

    enum CodingKeys: String, CodingKey {
        case seriesId = "series_id"
        case dateTime = "date_time"
        case channel
        case title
        case titleMatchMode = "title_match_mode"
        case keywordQuery = "keyword_query"
        case recentOnly = "recent_only"
        case startPadding = "start_padding"
        case endPadding = "end_padding"
        case maxEpisodesToKeep = "max_episodes_to_keep"
        case server
    }

    public init(
        seriesId: String,
        dateTime: TimeInterval? = nil,
        channel: String? = nil,
        title: String? = nil,
        titleMatchMode: String? = nil,
        keywordQuery: String? = nil,
        recentOnly: Bool? = nil,
        startPadding: Int? = nil,
        endPadding: Int? = nil,
        maxEpisodesToKeep: Int? = nil,
        server: String? = nil
    ) {
        self.seriesId = seriesId
        self.dateTime = dateTime
        self.channel = channel
        self.title = title
        self.titleMatchMode = titleMatchMode
        self.keywordQuery = keywordQuery
        self.recentOnly = recentOnly
        self.startPadding = startPadding
        self.endPadding = endPadding
        self.maxEpisodesToKeep = maxEpisodesToKeep
        self.server = server
    }
}
