import Foundation

public struct DeviceInfo: Identifiable, Codable, Sendable {
    public let id: String
    public let name: String
}

public struct DeviceListEntry: Identifiable, Codable, Sendable {
    public let id: String
    public let name: String
    public let lastSeenAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case lastSeenAt = "last_seen_at"
    }
}

public struct DeviceRegisterResult: Identifiable, Codable, Sendable {
    public let id: String
    public let name: String
    public let isNew: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case isNew = "is_new"
    }
}
