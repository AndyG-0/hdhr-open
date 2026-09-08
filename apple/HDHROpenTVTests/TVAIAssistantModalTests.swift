import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVAIAssistantModalTests: XCTestCase {
    private func makeAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    func testShowsHeaderAndEmptyStatePrompt() throws {
        let view = TVAIAssistantModal(apiClient: makeAPIClient())

        XCTAssertNoThrow(try view.inspect().find(text: "AI Guide Assistant"))
        XCTAssertNoThrow(try view.inspect().find(text: "Use dictation or pick a suggestion above to search."))
    }

    func testShowsEveryQuickSuggestionChip() throws {
        let view = TVAIAssistantModal(apiClient: makeAPIClient())

        for suggestion in AIChatHelpers.quickSuggestions {
            XCTAssertNoThrow(try view.inspect().find(text: suggestion), "Missing suggestion chip: \(suggestion)")
        }
    }

    func testNewChatButtonDisabledWhenThereAreNoTurns() throws {
        let view = TVAIAssistantModal(apiClient: makeAPIClient())

        XCTAssertTrue(try view.inspect().find(button: "New Chat").isDisabled())
    }

    func testCloseButtonIsPresent() throws {
        let view = TVAIAssistantModal(apiClient: makeAPIClient())

        XCTAssertNoThrow(try view.inspect().find(button: "Close"))
    }

    func testSendButtonDisabledWhenInputEmpty() throws {
        let view = TVAIAssistantModal(apiClient: makeAPIClient())

        XCTAssertTrue(try view.inspect().find(button: "Send").isDisabled())
    }

    func testInputFieldAcceptsText() throws {
        let view = TVAIAssistantModal(apiClient: makeAPIClient())

        // Without ViewHosting, @State mutations from setInput() don't propagate
        // back into a freshly re-inspected view body, so we only confirm the
        // input field exists and accepts text here rather than re-reading the
        // Send button's disabled state afterward (see testSendButtonDisabledWhenInputEmpty
        // for the reliably-testable initial state).
        let textField = try view.inspect().find(ViewType.TextField.self)
        XCTAssertNoThrow(try textField.setInput("What's on tonight?"))
    }

    func testHidesThinkingIndicatorWhenNotSending() throws {
        let view = TVAIAssistantModal(apiClient: makeAPIClient())

        XCTAssertThrowsError(try view.inspect().find(text: "Thinking..."))
    }
}
