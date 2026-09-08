import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSAIAssistantSheetTests: XCTestCase {
    private func makeAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    func testShowsEmptyStatePromptByDefault() throws {
        let view = iOSAIAssistantSheet(apiClient: makeAPIClient())

        XCTAssertNoThrow(try view.inspect().find(text: "What can I help you find?"))
    }

    func testShowsEveryQuickSuggestionChip() throws {
        let view = iOSAIAssistantSheet(apiClient: makeAPIClient())

        for suggestion in AIChatHelpers.quickSuggestions {
            XCTAssertNoThrow(try view.inspect().find(text: suggestion), "Missing suggestion chip: \(suggestion)")
        }
    }

    func testNewChatButtonDisabledWhenThereAreNoTurns() throws {
        let view = iOSAIAssistantSheet(apiClient: makeAPIClient())

        // turns starts empty, so the toolbar's "New Chat" reset button has
        // nothing to reset and stays disabled.
        XCTAssertTrue(try view.inspect().find(button: "New Chat").isDisabled())
    }

    func testDoneButtonIsPresentAndEnabled() throws {
        let view = iOSAIAssistantSheet(apiClient: makeAPIClient())

        XCTAssertFalse(try view.inspect().find(button: "Done").isDisabled())
    }
}
