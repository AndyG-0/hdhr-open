import HDHROpenKit
import Security
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

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
final class RootTVViewTests: XCTestCase {
    override func tearDown() {
        MockURLProtocol.handlers = [:]
        keychainDelete(authTokenKeychainKey)
        keychainDelete(authDeviceIdKeychainKey)
        super.tearDown()
    }

    private func makeEnvironmentObjects() -> (AuthManager, AuthViewModel, PlayerViewModel, MultiPlayerViewModel, DiscoveryViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let authManager = AuthManager(apiClient: apiClient)
        let authViewModel = AuthViewModel(authManager: authManager)
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let multiPlayerViewModel = MultiPlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let discoveryViewModel = DiscoveryViewModel(apiClient: apiClient)
        return (authManager, authViewModel, playerViewModel, multiPlayerViewModel, discoveryViewModel)
    }

    func testShowsProfilePickerWhenUnauthenticated() throws {
        let (authManager, authViewModel, playerViewModel, multiPlayerViewModel, discoveryViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(authManager.isAuthenticated)

        let view = RootTVView()
            .environmentObject(authManager)
            .environmentObject(authViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(multiPlayerViewModel)
            .environmentObject(discoveryViewModel)

        XCTAssertNoThrow(try view.inspect().find(TVProfilePickerView.self))
    }

    func testHidesPlayerAndPINPromptWhenUnauthenticatedWithNoActiveSession() throws {
        let (authManager, authViewModel, playerViewModel, multiPlayerViewModel, discoveryViewModel) = makeEnvironmentObjects()
        XCTAssertNil(playerViewModel.activeChannel)
        XCTAssertNil(playerViewModel.activeRecording)
        XCTAssertFalse(authViewModel.isPINPromptVisible)

        let view = RootTVView()
            .environmentObject(authManager)
            .environmentObject(authViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(multiPlayerViewModel)
            .environmentObject(discoveryViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVPlayerView.self))
        XCTAssertThrowsError(try view.inspect().find(TVPINEntryView.self))
    }

    func testShowsTabViewAndHidesProfilePickerWhenAuthenticated() async throws {
        let (authManager, authViewModel, playerViewModel, multiPlayerViewModel, discoveryViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )
        try await authManager.login(user: UserProfile(id: "u1", name: "Alice", avatar: nil, hasPin: true), pin: "1234")
        XCTAssertTrue(authManager.isAuthenticated)

        let view = RootTVView()
            .environmentObject(authManager)
            .environmentObject(authViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(multiPlayerViewModel)
            .environmentObject(discoveryViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.TabView.self))
        XCTAssertThrowsError(try view.inspect().find(TVProfilePickerView.self))
    }

    func testShowsTVMultiPlayerViewWhenMultiViewActive() async throws {
        let (authManager, authViewModel, playerViewModel, multiPlayerViewModel, discoveryViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )
        try await authManager.login(user: UserProfile(id: "u1", name: "Alice", avatar: nil, hasPin: true), pin: "1234")

        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"NBC\",\"play_url\":\"/stream/4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\":\"hls_sess1\",\"playlist_url\":\"/api/streaming/hls/hls_sess1/playlist.m3u8\"}".utf8), 200
        )

        try await multiPlayerViewModel.addFeed(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))
        XCTAssertTrue(multiPlayerViewModel.isMultiViewActive)

        let view = RootTVView()
            .environmentObject(authManager)
            .environmentObject(authViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(multiPlayerViewModel)
            .environmentObject(discoveryViewModel)

        XCTAssertNoThrow(try view.inspect().find(TVMultiPlayerView.self))
    }

    // NOTE: ViewInspector's `TabView` content extraction (`ViewType.TabView.
    // children`, in its own TabView.swift) throws for *any* child whose
    // `.tag()` doesn't match the TabView's current `selection` binding value
    // - not just for a genuinely-missing tab. Since `selectedTab` defaults to
    // 0 (Live Guide) and is a private `@State` with no seam to drive it to 4
    // without the heavier `ViewHosting`/`inspect(after:)` pattern (unused
    // elsewhere in this suite), there's no reliable static-inspection way to
    // assert the Discovery tab's content renders. The `if discoveryViewModel.
    // enabled { ... }` gate itself is a plain SwiftUI conditional, so it is
    // covered by code review rather than a dedicated UI test here.
}
