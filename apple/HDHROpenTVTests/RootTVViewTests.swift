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

    private func makeEnvironmentObjects() -> (AuthManager, AuthViewModel, PlayerViewModel, MultiPlayerViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let authManager = AuthManager(apiClient: apiClient)
        let authViewModel = AuthViewModel(authManager: authManager)
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let multiPlayerViewModel = MultiPlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        return (authManager, authViewModel, playerViewModel, multiPlayerViewModel)
    }

    func testShowsProfilePickerWhenUnauthenticated() throws {
        let (authManager, authViewModel, playerViewModel, multiPlayerViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(authManager.isAuthenticated)

        let view = RootTVView()
            .environmentObject(authManager)
            .environmentObject(authViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(multiPlayerViewModel)

        XCTAssertNoThrow(try view.inspect().find(TVProfilePickerView.self))
    }

    func testHidesPlayerAndPINPromptWhenUnauthenticatedWithNoActiveSession() throws {
        let (authManager, authViewModel, playerViewModel, multiPlayerViewModel) = makeEnvironmentObjects()
        XCTAssertNil(playerViewModel.activeChannel)
        XCTAssertNil(playerViewModel.activeRecording)
        XCTAssertFalse(authViewModel.isPINPromptVisible)

        let view = RootTVView()
            .environmentObject(authManager)
            .environmentObject(authViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(multiPlayerViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVPlayerView.self))
        XCTAssertThrowsError(try view.inspect().find(TVPINEntryView.self))
    }

    func testShowsTabViewAndHidesProfilePickerWhenAuthenticated() async throws {
        let (authManager, authViewModel, playerViewModel, multiPlayerViewModel) = makeEnvironmentObjects()
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

        XCTAssertNoThrow(try view.inspect().find(ViewType.TabView.self))
        XCTAssertThrowsError(try view.inspect().find(TVProfilePickerView.self))
    }

    func testShowsTVMultiPlayerViewWhenMultiViewActive() async throws {
        let (authManager, authViewModel, playerViewModel, multiPlayerViewModel) = makeEnvironmentObjects()
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

        XCTAssertNoThrow(try view.inspect().find(TVMultiPlayerView.self))
    }
}
