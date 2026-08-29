import SwiftUI
import HDHROpenKit

@main
struct HDHROpeniOSApp: App {
    @StateObject private var environment = AppEnvironment()

    var body: some Scene {
        WindowGroup {
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
                .task {
                    environment.serverDiscovery.startDiscovery()
                    await environment.authManager.restoreSession()
                    if !environment.authManager.isAuthenticated {
                        await environment.authManager.fetchProfiles()
                    }
                }
        }
    }
}
