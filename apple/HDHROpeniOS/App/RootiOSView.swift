import HDHROpenKit
import SwiftUI

public struct RootiOSView: View {
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var authViewModel: AuthViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @EnvironmentObject private var multiPlayerViewModel: MultiPlayerViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @EnvironmentObject private var discoveryViewModel: DiscoveryViewModel

    @State private var selectedTab = 0

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

                    if discoveryViewModel.enabled {
                        NavigationStack {
                            iOSDiscoveryView()
                        }
                        .tabItem {
                            Label("Discovery", systemImage: "sparkles")
                        }
                        .tag(4)
                    }
                }
                .task {
                    // Primes `enabled` for a fresh login from the profile
                    // picker - a restored session is already primed by
                    // HDHROpeniOSApp's own `.task` before this TabView ever
                    // mounts.
                    await discoveryViewModel.loadData()
                }
                .onChange(of: selectedTab) { _, newTab in
                    if newTab == 0 {
                        Task { await guideViewModel.loadData() }
                    } else if newTab == 1 {
                        Task { await recordingsViewModel.loadData() }
                    } else if newTab == 4 {
                        Task { await discoveryViewModel.loadData() }
                    }
                }

                if multiPlayerViewModel.isMultiViewActive {
                    iOSMultiPlayerView()
                        .transition(.opacity)
                        .zIndex(101)
                } else if playerViewModel.activeChannel != nil || playerViewModel.activeRecording != nil {
                    iOSPlayerView()
                        .transition(.opacity)
                        .zIndex(100)
                }
            }
        }
        .animation(
            .easeInOut(duration: 0.25),
            value: multiPlayerViewModel.isMultiViewActive || playerViewModel.activeChannel != nil || playerViewModel.activeRecording != nil
        )
    }
}
