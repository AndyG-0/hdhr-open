import HDHROpenKit
import Security
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

private let authTokenKeychainKey = "org.hdhropen.client.bearerToken"
private let authDeviceIdKeychainKey = "org.hdhropen.client.deviceId"

/// `PlaybackPreferences` persists `autoSkipCommercialsEnabled` to
/// `UserDefaults.standard` under this key (mirrored from the private
/// constant in PlaybackPreferences.swift). Save/restore it in setUp/tearDown
/// so a test that turns the preference on never leaks it into another test
/// via the shared, disk-backed UserDefaults.standard.
private let autoSkipCommercialsDefaultsKey = "org.hdhropen.client.autoSkipCommercialsEnabled"

private func keychainDelete(_ key: String) {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrAccount as String: key
    ]
    SecItemDelete(query as CFDictionary)
}

@MainActor
final class iOSSettingsViewTests: XCTestCase {
    private var savedAutoSkipDefaultsValue: Bool?

    override func setUp() {
        super.setUp()
        if UserDefaults.standard.object(forKey: autoSkipCommercialsDefaultsKey) != nil {
            savedAutoSkipDefaultsValue = UserDefaults.standard.bool(forKey: autoSkipCommercialsDefaultsKey)
        }
        UserDefaults.standard.removeObject(forKey: autoSkipCommercialsDefaultsKey)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        keychainDelete(authTokenKeychainKey)
        keychainDelete(authDeviceIdKeychainKey)
        if let savedAutoSkipDefaultsValue {
            UserDefaults.standard.set(savedAutoSkipDefaultsValue, forKey: autoSkipCommercialsDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: autoSkipCommercialsDefaultsKey)
        }
        super.tearDown()
    }

    private func makeEnvironmentObjects() -> (SettingsViewModel, ServerDiscovery, AuthManager, ThemeManager, PlaybackPreferences) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let serverDiscovery = ServerDiscovery(session: MockURLProtocol.makeSession())
        return (
            SettingsViewModel(apiClient: apiClient, serverDiscovery: serverDiscovery),
            serverDiscovery,
            AuthManager(apiClient: apiClient),
            ThemeManager(),
            PlaybackPreferences()
        )
    }

    func testShowsAppearanceAndServerConnectionSections() throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        let view = iOSSettingsView()
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertNoThrow(try view.inspect().find(text: "Appearance"))
        XCTAssertNoThrow(try view.inspect().find(iOSServerConnectionFields.self))
    }

    func testShowsPlaybackSectionWithAutoSkipCommercialsToggle() throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        XCTAssertFalse(playbackPreferences.autoSkipCommercialsEnabled)

        let view = iOSSettingsView()
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertNoThrow(try view.inspect().find(text: "Auto-skip commercials"))
        let toggle = try view.inspect().find(ViewType.Toggle.self)
        XCTAssertEqual(try toggle.isOn(), false)
    }

    func testHidesProfileSectionWhenLoggedOut() throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        XCTAssertNil(authManager.currentUser)

        let view = iOSSettingsView()
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertThrowsError(try view.inspect().find(text: "Logout"))
    }

    func testHidesTranscodePresetsSectionWhenEmpty() throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        XCTAssertTrue(settingsViewModel.transcodePresets.isEmpty)

        let view = iOSSettingsView()
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertThrowsError(try view.inspect().find(text: "Transcode Presets"))
    }

    func testShowsProfileSectionAndLogoutButtonWhenLoggedIn() async throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
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
            .environmentObject(playbackPreferences)

        XCTAssertNoThrow(try view.inspect().find(text: "Alice"))
        XCTAssertNoThrow(try view.inspect().find(button: "Logout"))
    }

    func testShowsTranscodePresetsSectionWhenLoaded() async throws {
        let (settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
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
            .environmentObject(playbackPreferences)

        XCTAssertNoThrow(try view.inspect().find(text: "Transcode Presets"))
        XCTAssertNoThrow(try view.inspect().find(text: "Hardware"))
        XCTAssertNoThrow(try view.inspect().find(text: "HW"))
    }
}
