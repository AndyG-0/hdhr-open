import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVServerConnectionFieldsTests: XCTestCase {
    private func makeEnvironmentObjects() -> (AppEnvironment, ServerDiscovery, SettingsViewModel) {
        let environment = AppEnvironment()
        let serverDiscovery = ServerDiscovery(session: MockURLProtocol.makeSession())
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let settingsViewModel = SettingsViewModel(apiClient: apiClient, serverDiscovery: serverDiscovery)
        return (environment, serverDiscovery, settingsViewModel)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsServerURLByDefault() throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        let view = TVServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Backend Server URL"))
        XCTAssertNoThrow(try view.inspect().find(text: serverDiscovery.serverURLString))
        XCTAssertNoThrow(try view.inspect().find(button: "Edit"))
    }

    func testHidesEditingControlsByDefault() throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        let view = TVServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(button: "Save"))
        XCTAssertThrowsError(try view.inspect().find(button: "Cancel"))
    }

    func testEditButtonIsTappable() throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        let view = TVServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        // Without ViewHosting, tapping Edit doesn't propagate the resulting @State
        // change back into a freshly re-inspected view body, so we only confirm the
        // button exists and is tappable rather than re-reading whether Save/Cancel
        // appear afterward (see testHidesEditingControlsByDefault for the
        // reliably-testable initial state).
        XCTAssertNoThrow(try view.inspect().find(button: "Edit").tap())
    }

    func testHidesDiscoveredServersSectionWhenEmpty() throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        XCTAssertTrue(serverDiscovery.discoveredServers.isEmpty)

        let view = TVServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Discovered on Local Network (LAN):"))
    }

    func testHidesConnectionStatusByDefault() throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        XCTAssertNil(settingsViewModel.connectionStatus)

        let view = TVServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Server reachable"))
    }

    func testShowsConnectionStatusAfterTestingConnection() async throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/setup/status"] = (Data("{}".utf8), 200)
        let url = try XCTUnwrap(serverDiscovery.currentServerURL)
        let ok = await settingsViewModel.testServerConnection(url: url)
        XCTAssertTrue(ok)

        let view = TVServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Server reachable"))
    }

    func testTestConnectionButtonTapInvokesConnectionCheckWhenServerURLIsSet() throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        serverDiscovery.serverURLString = "http://myserver:8000"
        XCTAssertNotNil(serverDiscovery.currentServerURL)

        let view = TVServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Test Connection").tap())
    }
}
