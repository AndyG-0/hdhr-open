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
final class iOSSettingsViewTests: XCTestCase {
    override func tearDown() {
        MockURLProtocol.handlers = [:]
        keychainDelete(authTokenKeychainKey)
        keychainDelete(authDeviceIdKeychainKey)
        super.tearDown()
    }

    private func makeEnvironmentObjects() -> (SettingsViewModel, ServerDiscovery, AuthManager, ThemeManager) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let serverDiscovery = ServerDiscovery(session: MockURLProtocol.makeSession())
        return (
            SettingsViewModel(apiClient: apiClient, serverDiscovery: serverDiscovery),
            serverDiscovery,
            AuthManager(apiClient: apiClient),
            ThemeManager()
        )
    }

    func testShowsAppearanceAndServerConnectionSections() throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
        let view = iOSSettingsView()
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)

        XCTAssertNoThrow(try view.inspect().find(text: "Appearance"))
        XCTAssertNoThrow(try view.inspect().find(iOSServerConnectionFields.self))
    }

    func testHidesProfileSectionWhenLoggedOut() throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
        XCTAssertNil(authManager.currentUser)

        let view = iOSSettingsView()
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)

        XCTAssertThrowsError(try view.inspect().find(text: "Logout"))
    }

    func testHidesTranscodePresetsSectionWhenEmpty() throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
        XCTAssertTrue(settingsViewModel.transcodePresets.isEmpty)

        let view = iOSSettingsView()
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)

        XCTAssertThrowsError(try view.inspect().find(text: "Transcode Presets"))
    }

    func testShowsProfileSectionAndLogoutButtonWhenLoggedIn() async throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )
        try await authManager.login(user: UserProfile(id: "u1", name: "Alice", avatar: nil, hasPin: true), pin: "1234")
        XCTAssertNotNil(authManager.currentUser)

        let view = iOSSettingsView()
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)

        XCTAssertNoThrow(try view.inspect().find(text: "Alice"))
        XCTAssertNoThrow(try view.inspect().find(button: "Logout"))
    }

    func testShowsTranscodePresetsSectionWhenLoaded() async throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
        let presetsBody = """
        [{"id": "hw", "label": "Hardware", "description": "Fast", "input_args": [], "output_args": [], "hardware": true}]
        """
        MockURLProtocol.handlers["/api/streaming/transcode-presets"] = (Data(presetsBody.utf8), 200)
        await settingsViewModel.loadPresets()
        XCTAssertFalse(settingsViewModel.transcodePresets.isEmpty)

        let view = iOSSettingsView()
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)

        XCTAssertNoThrow(try view.inspect().find(text: "Transcode Presets"))
        XCTAssertNoThrow(try view.inspect().find(text: "Hardware"))
        XCTAssertNoThrow(try view.inspect().find(text: "HW"))
    }
}
