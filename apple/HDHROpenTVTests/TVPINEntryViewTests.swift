import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVPINEntryViewTests: XCTestCase {
    private func makeAuthViewModel() -> AuthViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        return AuthViewModel(authManager: AuthManager(apiClient: apiClient))
    }

    func testShowsPINPromptTitleForSelectedProfile() throws {
        let authViewModel = makeAuthViewModel()
        authViewModel.selectedProfile = UserProfile(id: "u1", name: "Alice", hasPin: true)

        let view = TVPINEntryView().environmentObject(authViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Enter PIN for Alice"))
    }

    func testHidesPINPromptTitleWhenNoProfileSelected() throws {
        let authViewModel = makeAuthViewModel()
        XCTAssertNil(authViewModel.selectedProfile)

        let view = TVPINEntryView().environmentObject(authViewModel)

        XCTAssertThrowsError(try view.inspect().find(textWhere: { value, _ in value.hasPrefix("Enter PIN for") }))
    }

    func testShowsErrorMessageWhenSet() throws {
        let authViewModel = makeAuthViewModel()
        authViewModel.selectedProfile = UserProfile(id: "u1", name: "Alice", hasPin: true)
        authViewModel.errorMessage = "Incorrect PIN"

        let view = TVPINEntryView().environmentObject(authViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Incorrect PIN"))
    }

    func testTappingDigitButtonsAppendsToPinInput() throws {
        let authViewModel = makeAuthViewModel()
        authViewModel.selectedProfile = UserProfile(id: "u1", name: "Alice", hasPin: true)
        XCTAssertEqual(authViewModel.pinInput, "")

        let view = TVPINEntryView().environmentObject(authViewModel)

        try view.inspect().find(button: "1").tap()
        try view.inspect().find(button: "2").tap()
        try view.inspect().find(button: "3").tap()

        XCTAssertEqual(authViewModel.pinInput, "123")
    }

    func testTappingCancelButtonResetsState() throws {
        let authViewModel = makeAuthViewModel()
        let profile = UserProfile(id: "u1", name: "Alice", hasPin: true)
        authViewModel.selectedProfile = profile
        authViewModel.pinInput = "12"
        authViewModel.isPINPromptVisible = true

        let view = TVPINEntryView().environmentObject(authViewModel)

        try view.inspect().find(button: "Cancel").tap()

        XCTAssertNil(authViewModel.selectedProfile)
        XCTAssertEqual(authViewModel.pinInput, "")
        XCTAssertFalse(authViewModel.isPINPromptVisible)
    }
}
