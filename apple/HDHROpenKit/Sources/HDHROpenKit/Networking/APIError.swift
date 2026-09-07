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
            return "Invalid server URL."
        case .networkError(let msg):
            return "Network connection error: \(msg)"
        case .serverError(let code, let msg):
            return "Server error (\(code)): \(msg)"
        case .unauthorized(let msg):
            return msg
        case .forbidden:
            return "Admin privileges required for this action."
        case .notFound(let resource):
            return "Resource not found: \(resource)"
        case .decodingError(let msg):
            return "Data parsing error: \(msg)"
        case .noActiveWatchSession:
            return "No active watch session."
        case .lockedOut(let msg):
            return msg
        case .crossDeviceSyncActive:
            return "SyncPlay and SharePlay can't run at the same time. Leave the current session first."
        }
    }
}
