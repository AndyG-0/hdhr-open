import SwiftUI
import HDHROpenKit

@main
struct HDHROpeniOSApp: App {
    @StateObject private var environment = AppEnvironment()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            ThemedRootView(environment: environment)
        }
        .onChange(of: scenePhase) { _, newPhase in
            // No general background playback support: once the app leaves
            // the foreground there's no legitimate reason to keep the
            // tuner reserved, so release it the same way the in-player
            // close button does. Exceptions: an active AirPlay session is
            // *meant* to keep playing on the external device once this app
            // backgrounds (CAST-2), and an active Picture in Picture
            // session is *meant* to keep playing in the system PiP window
            // once this app backgrounds (PIP-4) - tearing the player down
            // in either case here would kill it the instant the user
            // leaves the app.
            if newPhase == .background
                && !environment.playerViewModel.playerEngine.isExternalPlaybackActive
                && !environment.playerViewModel.playerEngine.isPictureInPictureActive
                && !environment.playerViewModel.sharePlayCoordinator.isSessionActive {
                environment.playerViewModel.closePlayer()
            }
        }
    }
}

// `.preferredColorScheme` needs to be recomputed whenever `themeMode`
// changes. Evaluating it directly in `HDHROpeniOSApp.body` doesn't work -
// SwiftUI only re-invokes a Scene's body when something it directly
// observes (here, only `environment`'s own `@Published` properties, of
// which there are none) changes; `themeManager` is a plain `let` on
// `AppEnvironment`, so its changes never propagate up. A real View that
// observes `themeManager` itself re-renders correctly instead.
private struct ThemedRootView: View {
    @ObservedObject var environment: AppEnvironment
    @ObservedObject var themeManager: ThemeManager

    init(environment: AppEnvironment) {
        self.environment = environment
        self.themeManager = environment.themeManager
    }

    var body: some View {
        RootiOSView()
            .environmentObject(environment)
            .environmentObject(environment.guideViewModel)
            .environmentObject(environment.recordingsViewModel)
            .environmentObject(environment.playerViewModel)
            .environmentObject(environment.tunerViewModel)
            .environmentObject(environment.settingsViewModel)
            .environmentObject(environment.authViewModel)
            .environmentObject(environment.authManager)
            .environmentObject(environment.serverDiscovery)
            .environmentObject(themeManager)
            .preferredColorScheme(themeManager.colorScheme)
            .task {
                environment.serverDiscovery.startDiscovery()
                await environment.authManager.restoreSession()
                if !environment.authManager.isAuthenticated {
                    await environment.authManager.fetchProfiles()
                }
            }
    }
}
