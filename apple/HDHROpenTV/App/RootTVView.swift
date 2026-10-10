import HDHROpenKit
import SwiftUI

public struct RootTVView: View {
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var authViewModel: AuthViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @EnvironmentObject private var multiPlayerViewModel: MultiPlayerViewModel
    @EnvironmentObject private var discoveryViewModel: DiscoveryViewModel

    @State private var selectedTab = 0

    public init() {}

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            if !authManager.isAuthenticated {
                TVProfilePickerView()
            } else if multiPlayerViewModel.isMultiViewActive {
                TVMultiPlayerView()
            } else if playerViewModel.activeChannel != nil || playerViewModel.activeRecording != nil {
                TVPlayerView()
            } else {
                mainTabView
            }

            if authViewModel.isPINPromptVisible {
                TVPINEntryView()
                    .transition(.opacity.combined(with: .scale))
            }
        }
    }

    private var mainTabView: some View {
        TabView(selection: $selectedTab) {
            TVGuideView()
                .tabItem {
                    Label("Live Guide", systemImage: "tv")
                }
                .tag(0)

            TVRecordingsView()
                .tabItem {
                    Label("DVR Library", systemImage: "recordingtape")
                }
                .tag(1)

            TVTunerStatusView()
                .tabItem {
                    Label("Tuners", systemImage: "antenna.radiowaves.left.and.right")
                }
                .tag(2)

            TVSettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape")
                }
                .tag(3)

            if discoveryViewModel.enabled {
                TVDiscoveryView()
                    .tabItem {
                        Label("Discovery", systemImage: "sparkles")
                    }
                    .tag(4)
            }
        }
        .task {
            // Primes `enabled` for a fresh login from the profile picker -
            // a restored session is already primed by HDHROpenTVApp's own
            // `.task` before this TabView ever mounts. There's no
            // `onChange(of: selectedTab)` handler on tvOS to re-trigger
            // this per-tab, so TVDiscoveryView's own `.task` covers
            // reloading its item list on every appearance.
            await discoveryViewModel.loadData()
        }
    }
}
