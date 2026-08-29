import Foundation
import SwiftUI

@MainActor
public final class AppEnvironment: ObservableObject {
    public let apiClient: APIClient
    public let authManager: AuthManager
    public let serverDiscovery: ServerDiscovery
    public let watchSessionManager: WatchSessionManager

    public let guideViewModel: GuideViewModel
    public let recordingsViewModel: RecordingsViewModel
    public let tunerViewModel: TunerViewModel
    public let settingsViewModel: SettingsViewModel
    public let authViewModel: AuthViewModel
    public let playerViewModel: PlayerViewModel

    public init(defaultURLString: String = "http://127.0.0.1:8000") {
        let discovery = ServerDiscovery(defaultURL: defaultURLString)
        let initialURL = discovery.currentServerURL ?? URL(string: defaultURLString)!
        let client = APIClient(baseURL: initialURL)
        let auth = AuthManager(apiClient: client)
        let watch = WatchSessionManager(apiClient: client)

        self.serverDiscovery = discovery
        self.apiClient = client
        self.authManager = auth
        self.watchSessionManager = watch

        self.guideViewModel = GuideViewModel(apiClient: client, watchSessionManager: watch)
        self.recordingsViewModel = RecordingsViewModel(apiClient: client)
        self.tunerViewModel = TunerViewModel(apiClient: client)
        self.settingsViewModel = SettingsViewModel(apiClient: client, serverDiscovery: discovery)
        self.authViewModel = AuthViewModel(authManager: auth)
        self.playerViewModel = PlayerViewModel(apiClient: client, watchSessionManager: watch)
    }

    public func setServerURL(_ url: URL) async {
        serverDiscovery.serverURLString = url.absoluteString
        await apiClient.setBaseURL(url)
        await authManager.restoreSession()
    }
}
