import Foundation

public enum APIError: LocalizedError, Sendable {
    case invalidURL
    case networkError(String)
    case serverError(statusCode: Int, message: String)
    case unauthorized(String)
    case forbidden
    case notFound(String)
    case decodingError(String)
    case noActiveWatchSession
    case lockedOut(String)
    case crossDeviceSyncActive

    public var errorDescription: String? {
        switch self {
        case .invalidURL:
            "Invalid server URL."
        case let .networkError(msg):
            "Network connection error: \(msg)"
        case let .serverError(code, msg):
            "Server error (\(code)): \(msg)"
        case let .unauthorized(msg):
            msg
        case .forbidden:
            "Admin privileges required for this action."
        case let .notFound(resource):
            "Resource not found: \(resource)"
        case let .decodingError(msg):
            "Data parsing error: \(msg)"
        case .noActiveWatchSession:
            "No active watch session."
        case let .lockedOut(msg):
            msg
        case .crossDeviceSyncActive:
            "SyncPlay and SharePlay can't run at the same time. Leave the current session first."
        }
    }
}
