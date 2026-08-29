import Foundation

public struct HDHomeRunGuideEntry: Identifiable, Codable, Sendable, Hashable {
    public var id: String {
        if let seriesId = seriesId, let start = start {
            return "\(seriesId)_\(start)_\(channelNumber ?? "")"
        }
        return "\(title)_\(start ?? 0)_\(channelNumber ?? "")"
    }

    public let seriesId: String?
    public let title: String
    public let episodeTitle: String?
    public let episodeNumber: String?
    public let synopsis: String?
    public let start: TimeInterval?
    public let end: TimeInterval?
    public let originalAirdate: String?
    public let imageUrl: String?
    public let channelNumber: String?

    enum CodingKeys: String, CodingKey {
        case seriesId = "series_id"
        case title
        case episodeTitle = "episode_title"
        case episodeNumber = "episode_number"
        case synopsis
        case start
        case end
        case originalAirdate = "original_airdate"
        case imageUrl = "image_url"
        case channelNumber = "channel_number"
    }

    public init(
        seriesId: String? = nil,
        title: String,
        episodeTitle: String? = nil,
        episodeNumber: String? = nil,
        synopsis: String? = nil,
        start: TimeInterval? = nil,
        end: TimeInterval? = nil,
        originalAirdate: String? = nil,
        imageUrl: String? = nil,
        channelNumber: String? = nil
    ) {
        self.seriesId = seriesId
        self.title = title
        self.episodeTitle = episodeTitle
        self.episodeNumber = episodeNumber
        self.synopsis = synopsis
        self.start = start
        self.end = end
        self.originalAirdate = originalAirdate
        self.imageUrl = imageUrl
        self.channelNumber = channelNumber
    }

    public var startDate: Date? {
        guard let start = start else { return nil }
        return Date(timeIntervalSince1970: start)
    }

    public var endDate: Date? {
        guard let end = end else { return nil }
        return Date(timeIntervalSince1970: end)
    }

    public var durationSeconds: TimeInterval? {
        guard let start = start, let end = end, end > start else { return nil }
        return end - start
    }

    public func isCurrentlyAiring(at timestamp: TimeInterval = Date().timeIntervalSince1970) -> Bool {
        guard let start = start, let end = end else { return false }
        return timestamp >= start && timestamp < end
    }

    public var progress: Double {
        guard let start = start, let end = end, end > start else { return 0 }
        let now = Date().timeIntervalSince1970
        if now <= start { return 0 }
        if now >= end { return 1.0 }
        return (now - start) / (end - start)
    }
}
