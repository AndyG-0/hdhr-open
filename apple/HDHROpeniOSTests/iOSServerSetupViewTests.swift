import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSServerSetupViewTests: XCTestCase {
    private func makeAuthManager() -> AuthManager {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        return AuthManager(apiClient: apiClient)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsServerConnectionSectionAndEmbeddedFields() throws {
        let authManager = makeAuthManager()
        let view = iOSServerSetupView().environmentObject(authManager)

        XCTAssertNoThrow(try view.inspect().find(text: "Server Connection"))
        XCTAssertNoThrow(try view.inspect().find(iOSServerConnectionFields.self))
    }

    func testShowsDoneButton() throws {
        let authManager = makeAuthManager()
        let view = iOSServerSetupView().environmentObject(authManager)

        XCTAssertNoThrow(try view.inspect().find(button: "Done"))
    }
}
