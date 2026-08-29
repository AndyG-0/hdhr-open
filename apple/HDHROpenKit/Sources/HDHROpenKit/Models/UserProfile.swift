import Foundation

public enum UserRole: String, Codable, Sendable {
    case admin
    case member
}

public struct UserProfile: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public let name: String
    public let avatar: String?
    public let hasPin: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case avatar
        case hasPin = "has_pin"
    }

    public init(id: String, name: String, avatar: String? = nil, hasPin: Bool = false) {
        self.id = id
        self.name = name
        self.avatar = avatar
        self.hasPin = hasPin
    }
}

public struct CurrentUser: Identifiable, Codable, Sendable, Hashable {
    public let id: String
    public let name: String
    public let avatar: String?
    public let role: UserRole
    public let token: String?

    public init(id: String, name: String, avatar: String? = nil, role: UserRole = .member, token: String? = nil) {
        self.id = id
        self.name = name
        self.avatar = avatar
        self.role = role
        self.token = token
    }

    public var isAdmin: Bool {
        role == .admin
    }
}

public struct UserPreferences: Codable, Sendable {
    public var theme: String?
    public var locale: String?

    public init(theme: String? = nil, locale: String? = nil) {
        self.theme = theme
        self.locale = locale
    }
}

public struct SetupStatus: Codable, Sendable {
    public let needsSetup: Bool

    enum CodingKeys: String, CodingKey {
        case needsSetup = "needs_setup"
    }
}

public struct HouseholdUser: Identifiable, Codable, Sendable {
    public let id: String
    public let name: String
    public let avatar: String?
    public let hasPin: Bool
    public let role: UserRole
    public let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case avatar
        case hasPin = "has_pin"
        case role
        case createdAt = "created_at"
    }
}
