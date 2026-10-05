import Foundation

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

    private let autoSkipCommercialsKey = "org.hdhropen.client.autoSkipCommercialsEnabled"

    public init() {
        autoSkipCommercialsEnabled = UserDefaults.standard.bool(forKey: "org.hdhropen.client.autoSkipCommercialsEnabled")
    }
}
