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
    public let multiPlayerViewModel: MultiPlayerViewModel
    public let themeManager: ThemeManager

    public init(defaultURLString: String = "http://127.0.0.1:8000") {
        let discovery = ServerDiscovery(defaultURL: defaultURLString)
        let initialURL = discovery.currentServerURL ?? URL(string: defaultURLString)!
        let client = APIClient(baseURL: initialURL)
        let auth = AuthManager(apiClient: client)
        let watch = WatchSessionManager(apiClient: client)

        serverDiscovery = discovery
        apiClient = client
        authManager = auth
        watchSessionManager = watch

        guideViewModel = GuideViewModel(apiClient: client, watchSessionManager: watch)
        recordingsViewModel = RecordingsViewModel(apiClient: client)
        tunerViewModel = TunerViewModel(apiClient: client)
        settingsViewModel = SettingsViewModel(apiClient: client, serverDiscovery: discovery)
        authViewModel = AuthViewModel(authManager: auth)
        playerViewModel = PlayerViewModel(apiClient: client, watchSessionManager: watch)
        multiPlayerViewModel = MultiPlayerViewModel(apiClient: client, watchSessionManager: watch)
        themeManager = ThemeManager()
    }

    public func setServerURL(_ url: URL) async {
        serverDiscovery.serverURLString = url.absoluteString
        await apiClient.setBaseURL(url)
        await authManager.restoreSession()

        async let guide: Void = guideViewModel.loadData()
        async let recordings: Void = recordingsViewModel.loadData()
        async let tuners: Void = tunerViewModel.loadData()
        async let settings: Void = settingsViewModel.loadData()
        async let profiles: Void = authManager.fetchProfiles()
        _ = await (guide, recordings, tuners, settings, profiles)
    }
}
