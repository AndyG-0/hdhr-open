import Foundation

/// The user-facing, persisted quality preference. `auto` lets the player's
/// buffer-drain/stall-gated logic pick the effective tier at runtime;
/// the others pin a fixed tier. `minimal` is reachable only via auto
/// step-down and is intentionally not a case here.
public enum VideoQuality: String, CaseIterable, Sendable {
    case auto
    case high
    case medium
    case low

    public var label: String {
        switch self {
        case .auto: "Auto"
        case .high: "High"
        case .medium: "Medium"
        case .low: "Low"
        }
    }

    /// The value sent to the backend's `quality` query/body param, or `nil`
    /// for `auto` (the caller supplies the auto-effective tier instead).
    public var backendValue: String? {
        switch self {
        case .auto: nil
        case .high: "high"
        case .medium: "medium"
        case .low: "low"
        }
    }
}

/// Per-device playback preferences - unlike server-synced, household-wide
/// settings, these describe what *this device* should do and are never sent
/// to the backend.
@MainActor
public final class PlaybackPreferences: ObservableObject {
    @Published public var autoSkipCommercialsEnabled: Bool {
        didSet {
            UserDefaults.standard.set(autoSkipCommercialsEnabled, forKey: autoSkipCommercialsKey)
        }
    }

    @Published public var videoQuality: VideoQuality {
        didSet {
            UserDefaults.standard.set(videoQuality.rawValue, forKey: videoQualityKey)
        }
    }

    private let autoSkipCommercialsKey = "org.hdhropen.client.autoSkipCommercialsEnabled"
    private let videoQualityKey = "org.hdhropen.client.videoQuality"

    public init() {
        autoSkipCommercialsEnabled = UserDefaults.standard.bool(forKey: "org.hdhropen.client.autoSkipCommercialsEnabled")
        let storedQuality = UserDefaults.standard.string(forKey: "org.hdhropen.client.videoQuality")
        videoQuality = storedQuality.flatMap(VideoQuality.init(rawValue:)) ?? .auto
    }
}
