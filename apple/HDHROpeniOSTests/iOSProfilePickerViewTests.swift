import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSProfilePickerViewTests: XCTestCase {
    private func makeViewModels() -> (AuthManager, AuthViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let authManager = AuthManager(apiClient: apiClient)
        return (authManager, AuthViewModel(authManager: authManager))
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsWhosWatchingTitle() throws {
        let (authManager, authViewModel) = makeViewModels()
        let view = iOSProfilePickerView()
            .environmentObject(authViewModel)
            .environmentObject(authManager)

        XCTAssertNoThrow(try view.inspect().find(text: "Who's Watching?"))
    }

    func testDisplaysFetchedProfilesInGrid() async throws {
        let (authManager, authViewModel) = makeViewModels()
        MockURLProtocol.handlers["/api/users"] = (Data("""
        [{"id":"u1","name":"Alice","has_pin":false},{"id":"u2","name":"Bob","has_pin":true}]
        """.utf8), 200)

        await authManager.fetchProfiles()
        XCTAssertEqual(authViewModel.profiles.count, 2)

        let view = iOSProfilePickerView()
            .environmentObject(authViewModel)
            .environmentObject(authManager)

        XCTAssertNoThrow(try view.inspect().find(text: "Alice"))
        XCTAssertNoThrow(try view.inspect().find(text: "Bob"))
    }

    func testShowsErrorMessageWhenProfileFetchFails() async throws {
        let (authManager, authViewModel) = makeViewModels()
        MockURLProtocol.handlers["/api/users"] = (Data("{\"detail\":\"server error\"}".utf8), 500)

        await authManager.fetchProfiles()
        let error = try XCTUnwrap(authManager.authError)

        let view = iOSProfilePickerView()
            .environmentObject(authViewModel)
            .environmentObject(authManager)

        XCTAssertNoThrow(try view.inspect().find(text: error))
    }
}
