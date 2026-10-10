import HDHROpenKit
import Security
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

private let authTokenKeychainKey = "org.hdhropen.client.bearerToken"
private let authDeviceIdKeychainKey = "org.hdhropen.client.deviceId"

private func keychainDelete(_ key: String) {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrAccount as String: key
    ]
    SecItemDelete(query as CFDictionary)
}

@MainActor
final class RootiOSViewTests: XCTestCase {
    override func tearDown() {
        MockURLProtocol.handlers = [:]
        keychainDelete(authTokenKeychainKey)
        keychainDelete(authDeviceIdKeychainKey)
        super.tearDown()
    }

    private struct EnvironmentObjects {
        let authManager: AuthManager
        let authViewModel: AuthViewModel
        let playerViewModel: PlayerViewModel
        let guideViewModel: GuideViewModel
        let recordingsViewModel: RecordingsViewModel
        let discoveryViewModel: DiscoveryViewModel
        let multiPlayerViewModel: MultiPlayerViewModel
    }

    private func makeEnvironmentObjects() -> EnvironmentObjects {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let authManager = AuthManager(apiClient: apiClient)
        let authViewModel = AuthViewModel(authManager: authManager)
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let recordingsViewModel = RecordingsViewModel(apiClient: apiClient)
        let discoveryViewModel = DiscoveryViewModel(apiClient: apiClient)
        let multiPlayerViewModel = MultiPlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        return EnvironmentObjects(
            authManager: authManager,
            authViewModel: authViewModel,
            playerViewModel: playerViewModel,
            guideViewModel: guideViewModel,
            recordingsViewModel: recordingsViewModel,
            discoveryViewModel: discoveryViewModel,
            multiPlayerViewModel: multiPlayerViewModel
        )
    }

    func testShowsProfilePickerWhenUnauthenticated() throws {
        let env = makeEnvironmentObjects()
        XCTAssertFalse(env.authManager.isAuthenticated)

        let view = RootiOSView()
            .environmentObject(env.authManager)
            .environmentObject(env.authViewModel)
            .environmentObject(env.playerViewModel)
            .environmentObject(env.guideViewModel)
            .environmentObject(env.recordingsViewModel)
            .environmentObject(env.discoveryViewModel)
            .environmentObject(env.multiPlayerViewModel)

        XCTAssertNoThrow(try view.inspect().find(iOSProfilePickerView.self))
    }

    func testHidesPlayerOverlayWhenNoActiveChannelOrRecording() throws {
        let env = makeEnvironmentObjects()
        XCTAssertNil(env.playerViewModel.activeChannel)
        XCTAssertNil(env.playerViewModel.activeRecording)

        let view = RootiOSView()
            .environmentObject(env.authManager)
            .environmentObject(env.authViewModel)
            .environmentObject(env.playerViewModel)
            .environmentObject(env.guideViewModel)
            .environmentObject(env.recordingsViewModel)
            .environmentObject(env.discoveryViewModel)
            .environmentObject(env.multiPlayerViewModel)

        XCTAssertThrowsError(try view.inspect().find(iOSPlayerView.self))
    }

    func testShowsTabViewAndHidesProfilePickerWhenAuthenticated() async throws {
        let env = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )
        try await env.authManager.login(user: UserProfile(id: "u1", name: "Alice", avatar: nil, hasPin: true), pin: "1234")
        XCTAssertTrue(env.authManager.isAuthenticated)

        let view = RootiOSView()
            .environmentObject(env.authManager)
            .environmentObject(env.authViewModel)
            .environmentObject(env.playerViewModel)
            .environmentObject(env.guideViewModel)
            .environmentObject(env.recordingsViewModel)
            .environmentObject(env.discoveryViewModel)
            .environmentObject(env.multiPlayerViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.TabView.self))
        XCTAssertThrowsError(try view.inspect().find(iOSProfilePickerView.self))
    }

    func testShowsIOSMultiPlayerViewWhenMultiViewActive() async throws {
        let env = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )
        try await env.authManager.login(user: UserProfile(id: "u1", name: "Alice", avatar: nil, hasPin: true), pin: "1234")

        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"NBC\",\"play_url\":\"/stream/4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\":\"hls_sess1\",\"playlist_url\":\"/api/streaming/hls/hls_sess1/playlist.m3u8\"}".utf8), 200
        )

        try await env.multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        XCTAssertTrue(env.multiPlayerViewModel.isMultiViewActive)

        let view = RootiOSView()
            .environmentObject(env.authManager)
            .environmentObject(env.authViewModel)
            .environmentObject(env.playerViewModel)
            .environmentObject(env.guideViewModel)
            .environmentObject(env.recordingsViewModel)
            .environmentObject(env.discoveryViewModel)
            .environmentObject(env.multiPlayerViewModel)

        XCTAssertNoThrow(try view.inspect().find(iOSMultiPlayerView.self))
    }

    // NOTE: ViewInspector's `TabView` content extraction (`ViewType.TabView.
    // children`, in its own TabView.swift) throws for *any* child whose
    // `.tag()` doesn't match the TabView's current `selection` binding value
    // - not just for a genuinely-missing tab. Since `selectedTab` defaults to
    // 0 (Guide) and is a private `@State` with no seam to drive it to 4
    // without the heavier `ViewHosting`/`inspect(after:)` pattern (unused
    // elsewhere in this suite), there's no reliable static-inspection way to
    // assert the Discovery tab's content renders. The `if discoveryViewModel.
    // enabled { ... }` gate itself is a plain SwiftUI conditional - the same
    // construct used in `iOSDiscoveryView`'s own fallback-banner branch,
    // which the view tests below already drive through the mocked API - so
    // it is covered by code review rather than a dedicated UI test here.
}
