import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

/// `PlaybackPreferences` persists `autoSkipCommercialsEnabled` to
/// `UserDefaults.standard` under this key (mirrored from the private
/// constant in PlaybackPreferences.swift). Save/restore it in setUp/tearDown
/// so a test that turns the preference on never leaks it into another test
/// via the shared, disk-backed UserDefaults.standard.
private let autoSkipCommercialsDefaultsKey = "org.hdhropen.client.autoSkipCommercialsEnabled"

@MainActor
final class TVSettingsViewTests: XCTestCase {
    private var savedAutoSkipDefaultsValue: Bool?

    private func makeEnvironmentObjects() -> (AppEnvironment, SettingsViewModel, ServerDiscovery, AuthManager, ThemeManager, PlaybackPreferences) {
        let environment = AppEnvironment()
        let serverDiscovery = ServerDiscovery(session: MockURLProtocol.makeSession())
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let settingsViewModel = SettingsViewModel(apiClient: apiClient, serverDiscovery: serverDiscovery)
        let authManager = AuthManager(apiClient: apiClient)
        return (environment, settingsViewModel, serverDiscovery, authManager, ThemeManager(), PlaybackPreferences())
    }

    override func setUp() {
        super.setUp()
        if UserDefaults.standard.object(forKey: autoSkipCommercialsDefaultsKey) != nil {
            savedAutoSkipDefaultsValue = UserDefaults.standard.bool(forKey: autoSkipCommercialsDefaultsKey)
        }
        UserDefaults.standard.removeObject(forKey: autoSkipCommercialsDefaultsKey)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        if let savedAutoSkipDefaultsValue {
            UserDefaults.standard.set(savedAutoSkipDefaultsValue, forKey: autoSkipCommercialsDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: autoSkipCommercialsDefaultsKey)
        }
        super.tearDown()
    }

    func testShowsAppearanceAndServerConnectionSections() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertNoThrow(try view.inspect().find(text: "Appearance"))
        XCTAssertNoThrow(try view.inspect().find(text: "Server Connection"))
        XCTAssertNoThrow(try view.inspect().find(TVServerConnectionFields.self))
    }

    func testShowsPlaybackSectionWithAutoSkipCommercialsToggle() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        XCTAssertFalse(playbackPreferences.autoSkipCommercialsEnabled)

        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertNoThrow(try view.inspect().find(text: "Playback"))
        XCTAssertNoThrow(try view.inspect().find(text: "Auto-skip commercials"))
        let toggle = try view.inspect().find(ViewType.Toggle.self)
        XCTAssertEqual(try toggle.isOn(), false)
    }

    func testShowsEveryThemeModeOption() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        for mode in ThemeMode.allCases {
            XCTAssertNoThrow(try view.inspect().find(text: mode.label), "Missing theme mode: \(mode.label)")
        }
    }

    func testHidesProfileSectionDetailsWhenLoggedOut() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        XCTAssertNil(authManager.currentUser)

        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertThrowsError(try view.inspect().find(button: "Switch Profile / Logout"))
    }

    func testHidesTranscodePresetsSectionWhenEmpty() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        XCTAssertTrue(settingsViewModel.transcodePresets.isEmpty)

        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertThrowsError(try view.inspect().find(text: "Transcoder Presets"))
    }

    func testShowsTranscodePresetsSectionWhenLoaded() async throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/streaming/transcode-presets"] = (Data("""
        [{"id":"hw1","label":"Hardware H.264","description":"Uses VideoToolbox","input_args":[],"output_args":[],"hardware":true}]
        """.utf8), 200)
        await settingsViewModel.loadPresets()
        XCTAssertEqual(settingsViewModel.transcodePresets.count, 1)

        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertNoThrow(try view.inspect().find(text: "Transcoder Presets"))
        XCTAssertNoThrow(try view.inspect().find(text: "Hardware H.264"))
        XCTAssertNoThrow(try view.inspect().find(text: "HW"))
    }
}
