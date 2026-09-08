import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVServerSetupViewTests: XCTestCase {
    private func makeEnvironmentObjects() -> (AppEnvironment, ServerDiscovery, SettingsViewModel, AuthManager) {
        let environment = AppEnvironment()
        let serverDiscovery = ServerDiscovery(session: MockURLProtocol.makeSession())
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let settingsViewModel = SettingsViewModel(apiClient: apiClient, serverDiscovery: serverDiscovery)
        let authManager = AuthManager(apiClient: apiClient)
        return (environment, serverDiscovery, settingsViewModel, authManager)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsTitleAndConnectionFields() throws {
        let (environment, serverDiscovery, settingsViewModel, authManager) = makeEnvironmentObjects()
        let view = TVServerSetupView()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)
            .environmentObject(authManager)

        XCTAssertNoThrow(try view.inspect().find(text: "Server Setup"))
        XCTAssertNoThrow(try view.inspect().find(TVServerConnectionFields.self))
    }

    func testShowsDoneButton() throws {
        let (environment, serverDiscovery, settingsViewModel, authManager) = makeEnvironmentObjects()
        let view = TVServerSetupView()
            .environmentObject(environment)
            .environmentObject(serverDiscovery)
            .environmentObject(settingsViewModel)
            .environmentObject(authManager)

        XCTAssertNoThrow(try view.inspect().find(button: "Done"))
    }
}
