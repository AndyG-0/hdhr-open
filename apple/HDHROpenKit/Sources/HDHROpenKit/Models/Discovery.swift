import Foundation

/// Wire shape for `GET /api/discovery`: upcoming guide airings recommended
/// from the household's recording history, or a non-personalized "New &
/// Notable" fallback when there's no history yet. `items` reuses
/// `HDHomeRunGuideEntry` unchanged - the backend returns the exact same
/// guide-airing JSON shape used elsewhere in the guide.
public struct DiscoveryResponse: Codable, Sendable {
    public let enabled: Bool
    public let hasProfile: Bool
    public let items: [HDHomeRunGuideEntry]

    enum CodingKeys: String, CodingKey {
        case enabled
        case hasProfile = "has_profile"
        case items
    }

    public init(enabled: Bool, hasProfile: Bool, items: [HDHomeRunGuideEntry]) {
        self.enabled = enabled
        self.hasProfile = hasProfile
        self.items = items
    }
}
