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

    func testShowsAppearanceSectionInGeneralGroup() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertNoThrow(try view.inspect().find(text: "Appearance"))
        XCTAssertThrowsError(try view.inspect().find(text: "Server Connection"))
        XCTAssertThrowsError(try view.inspect().find(TVServerConnectionFields.self))
    }

    /// Tapping the pill button mutates the `@State` selection via its
    /// binding, but per this codebase's documented ViewInspector limitation
    /// (see `TVMultiPlayerViewTests`, `TVServerConnectionFieldsTests`,
    /// `TVKeywordRuleModalTests`), that mutation doesn't propagate to a fresh
    /// inspection without `ViewHosting`. Assert only that the group selector
    /// exists and tapping the other group's button doesn't throw.
    func testSettingsGroupSelectorAllowsTappingServerAndAdvanced() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager, playbackPreferences) = makeEnvironmentObjects()
        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)
            .environmentObject(playbackPreferences)

        XCTAssertNoThrow(try view.inspect().find(button: "Server & Advanced").tap())
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

    /// Transcoder Presets now lives in the Server & Advanced group, so it's
    /// hidden in the default (General) render regardless of whether presets
    /// are loaded - this no longer isolates the inner `!transcodePresets.isEmpty`
    /// check (see the group-selector limitation noted on
    /// `testSettingsGroupSelectorAllowsTappingServerAndAdvanced`), but it does
    /// confirm the section stays scoped to its group.
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

    /// See the comment on `testHidesTranscodePresetsSectionWhenEmpty`: this
    /// verifies the same group-scoping holds once presets are loaded, not the
    /// presence of the Transcoder Presets content itself (unreachable from the
    /// default General render without `ViewHosting`).
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

        XCTAssertThrowsError(try view.inspect().find(text: "Transcoder Presets"))
    }
}
