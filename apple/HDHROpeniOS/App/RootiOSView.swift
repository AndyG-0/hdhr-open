import SwiftUI
import HDHROpenKit

public struct RootiOSView: View {
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var authViewModel: AuthViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel

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
                .onChange(of: selectedTab) { _, newTab in
                    if newTab == 0 {
                        Task { await guideViewModel.loadData() }
                    } else if newTab == 1 {
                        Task { await recordingsViewModel.loadData() }
                    }
                }

                if playerViewModel.activeChannel != nil || playerViewModel.activeRecording != nil {
                    iOSPlayerView()
                        .transition(.opacity)
                        .zIndex(100)
                }
            }
        }
        .animation(.easeInOut(duration: 0.25), value: playerViewModel.activeChannel != nil || playerViewModel.activeRecording != nil)
    }
}
