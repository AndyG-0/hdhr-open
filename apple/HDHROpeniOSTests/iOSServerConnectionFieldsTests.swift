import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSServerConnectionFieldsTests: XCTestCase {
    private func makeEnvironmentObjects() -> (AppEnvironment, ServerDiscovery, SettingsViewModel) {
        let serverDiscovery = ServerDiscovery(session: MockURLProtocol.makeSession())
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let settingsViewModel = SettingsViewModel(apiClient: apiClient, serverDiscovery: serverDiscovery)
        let environment = AppEnvironment()
        return (environment, serverDiscovery, settingsViewModel)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsConnectAndTestConnectionButtons() throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        let view = iOSServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Connect"))
        XCTAssertNoThrow(try view.inspect().find(button: "Test Connection"))
    }

    func testConnectButtonDisabledWhenInputIsEmpty() throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        let view = iOSServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        // @State serverURLInput starts as "" (the .onAppear seed from
        // serverDiscovery.serverURLString doesn't fire without ViewHosting),
        // and URL(string: "") is nil, so Connect stays disabled.
        XCTAssertTrue(try view.inspect().find(button: "Connect").isDisabled())
    }

    func testShowsReachableStatusAfterSuccessfulConnectionTest() async throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/setup/status"] = (Data("{}".utf8), 200)
        let reachable = try await settingsViewModel.testServerConnection(url: XCTUnwrap(URL(string: "http://localhost:8000")))
        XCTAssertTrue(reachable)
        XCTAssertEqual(settingsViewModel.connectionStatus, "Server reachable")

        let view = iOSServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Server reachable"))
    }

    func testShowsUnreachableStatusAfterFailedConnectionTest() async throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/setup/status"] = (Data("{}".utf8), 500)
        let reachable = try await settingsViewModel.testServerConnection(url: XCTUnwrap(URL(string: "http://localhost:8000")))
        XCTAssertFalse(reachable)
        XCTAssertEqual(settingsViewModel.connectionStatus, "Server unreachable")

        let view = iOSServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Server unreachable"))
    }

    func testTestConnectionButtonTapInvokesConnectionCheckWhenServerURLIsSet() throws {
        let (environment, serverDiscovery, settingsViewModel) = makeEnvironmentObjects()
        serverDiscovery.serverURLString = "http://myserver:8000"
        XCTAssertNotNil(serverDiscovery.currentServerURL)

        let view = iOSServerConnectionFields()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Test Connection").tap())
    }
}
