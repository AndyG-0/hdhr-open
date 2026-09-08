import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVSettingsViewTests: XCTestCase {
    private func makeEnvironmentObjects() -> (AppEnvironment, SettingsViewModel, ServerDiscovery, AuthManager, ThemeManager) {
        let environment = AppEnvironment()
        let serverDiscovery = ServerDiscovery(session: MockURLProtocol.makeSession())
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let settingsViewModel = SettingsViewModel(apiClient: apiClient, serverDiscovery: serverDiscovery)
        let authManager = AuthManager(apiClient: apiClient)
        return (environment, settingsViewModel, serverDiscovery, authManager, ThemeManager())
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsAppearanceAndServerConnectionSections() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)

        XCTAssertNoThrow(try view.inspect().find(text: "Appearance"))
        XCTAssertNoThrow(try view.inspect().find(text: "Server Connection"))
        XCTAssertNoThrow(try view.inspect().find(TVServerConnectionFields.self))
    }

    func testShowsEveryThemeModeOption() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)

        for mode in ThemeMode.allCases {
            XCTAssertNoThrow(try view.inspect().find(text: mode.label), "Missing theme mode: \(mode.label)")
        }
    }

    func testHidesProfileSectionDetailsWhenLoggedOut() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
        XCTAssertNil(authManager.currentUser)

        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)

        XCTAssertThrowsError(try view.inspect().find(button: "Switch Profile / Logout"))
    }

    func testHidesTranscodePresetsSectionWhenEmpty() throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
        XCTAssertTrue(settingsViewModel.transcodePresets.isEmpty)

        let view = TVSettingsView()
            .environmentObject(environment)
            .environmentObject(settingsViewModel)
            .environmentObject(serverDiscovery)
            .environmentObject(authManager)
            .environmentObject(themeManager)

        XCTAssertThrowsError(try view.inspect().find(text: "Transcoder Presets"))
    }

    func testShowsTranscodePresetsSectionWhenLoaded() async throws {
        let (environment, settingsViewModel, serverDiscovery, authManager, themeManager) = makeEnvironmentObjects()
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

        XCTAssertNoThrow(try view.inspect().find(text: "Transcoder Presets"))
        XCTAssertNoThrow(try view.inspect().find(text: "Hardware H.264"))
        XCTAssertNoThrow(try view.inspect().find(text: "HW"))
    }
}
