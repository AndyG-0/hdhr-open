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

    private func makeEnvironmentObjects() -> (AuthManager, AuthViewModel, PlayerViewModel, GuideViewModel, RecordingsViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let authManager = AuthManager(apiClient: apiClient)
        let authViewModel = AuthViewModel(authManager: authManager)
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let recordingsViewModel = RecordingsViewModel(apiClient: apiClient)
        return (authManager, authViewModel, playerViewModel, guideViewModel, recordingsViewModel)
    }

    func testShowsProfilePickerWhenUnauthenticated() throws {
        let (authManager, authViewModel, playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(authManager.isAuthenticated)

        let view = RootiOSView()
            .environmentObject(authManager)
            .environmentObject(authViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(iOSProfilePickerView.self))
    }

    func testHidesPlayerOverlayWhenNoActiveChannelOrRecording() throws {
        let (authManager, authViewModel, playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertNil(playerViewModel.activeChannel)
        XCTAssertNil(playerViewModel.activeRecording)

        let view = RootiOSView()
            .environmentObject(authManager)
            .environmentObject(authViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(iOSPlayerView.self))
    }

    func testShowsTabViewAndHidesProfilePickerWhenAuthenticated() async throws {
        let (authManager, authViewModel, playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )
        try await authManager.login(user: UserProfile(id: "u1", name: "Alice", avatar: nil, hasPin: true), pin: "1234")
        XCTAssertTrue(authManager.isAuthenticated)

        let view = RootiOSView()
            .environmentObject(authManager)
            .environmentObject(authViewModel)
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.TabView.self))
        XCTAssertThrowsError(try view.inspect().find(iOSProfilePickerView.self))
    }
}
