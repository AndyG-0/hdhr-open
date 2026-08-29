import SwiftUI
import HDHROpenKit

public struct RootTVView: View {
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var authViewModel: AuthViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel

    @State private var selectedTab: Int = 0

    public init() {}

    public var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if !authManager.isAuthenticated {
                TVProfilePickerView()
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
        }
    }
}
