import SwiftUI
import HDHROpenKit

public struct RootiOSView: View {
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var authViewModel: AuthViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel

    @State private var selectedTab: Int = 0

    public init() {}

    public var body: some View {
        ZStack {
            if !authManager.isAuthenticated {
                iOSProfilePickerView()
            } else {
                TabView(selection: $selectedTab) {
                    NavigationStack {
                        iOSGuideView()
                    }
                    .tabItem {
                        Label("Guide", systemImage: "tv")
                    }
                    .tag(0)

                    NavigationStack {
                        iOSRecordingsView()
                    }
                    .tabItem {
                        Label("Recordings", systemImage: "recordingtape")
                    }
                    .tag(1)

                    NavigationStack {
                        iOSTunerStatusView()
                    }
                    .tabItem {
                        Label("Tuners", systemImage: "antenna.radiowaves.left.and.right")
                    }
                    .tag(2)

                    NavigationStack {
                        iOSSettingsView()
                    }
                    .tabItem {
                        Label("Settings", systemImage: "gearshape")
                    }
                    .tag(3)
                }
            }
        }
        .fullScreenCover(isPresented: Binding(
            get: { playerViewModel.activeChannel != nil || playerViewModel.activeRecording != nil },
            set: { if !$0 { playerViewModel.closePlayer() } }
        )) {
            iOSPlayerView()
        }
    }
}
