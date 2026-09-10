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

    // MARK: - REV-APL-19: ViewHosting-driven interaction coverage

    /// Responds after an artificial delay, so a test can reliably observe `sendPrompt`'s
    /// synchronous `isSending = true` state (set before its network `Task` runs) without
    /// racing the otherwise-instant `MockURLProtocol`.
    private final class DelayedAIURLProtocol: URLProtocol {
        static var handlers: [String: (Data, Int)] = [:]
        static let delay: TimeInterval = 0.2

        override class func canInit(with _: URLRequest) -> Bool {
            true
        }

        override class func canonicalRequest(for request: URLRequest) -> URLRequest {
            request
        }

        override func startLoading() {
            let path = request.url?.path ?? ""
            let (data, status) = DelayedAIURLProtocol.handlers[path] ?? (Data("{}".utf8), 404)
            DispatchQueue.main.asyncAfter(deadline: .now() + DelayedAIURLProtocol.delay) { [self] in
                let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
                client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                client?.urlProtocol(self, didLoad: data)
                client?.urlProtocolDidFinishLoading(self)
            }
        }

        override func stopLoading() {}

        static func makeSession() -> URLSession {
            let config = URLSessionConfiguration.ephemeral
            config.protocolClasses = [DelayedAIURLProtocol.self]
            return URLSession(configuration: config)
        }
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        DelayedAIURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testTappingSuggestionShowsThinkingIndicatorImmediately() async throws {
        DelayedAIURLProtocol.handlers["/api/ai/chat"] = (Data("data: {\"type\":\"done\"}\n\n".utf8), 200)
        let client = try APIClient(baseURL: XCTUnwrap(URL(string: "http://localhost:8000")), session: DelayedAIURLProtocol.makeSession())
        let sut = iOSAIAssistantSheet(apiClient: client)
        let suggestion = try XCTUnwrap(AIChatHelpers.quickSuggestions.first)

        let exp1 = sut.inspection.inspect(after: 0) { view in
            try view.find(button: suggestion).tap()
        }
        let exp2 = sut.inspection.inspect(after: 0.05) { view in
            XCTAssertNoThrow(try view.find(text: "Thinking..."))
        }
        let exp3 = sut.inspection.inspect(after: DelayedAIURLProtocol.delay + 1.0) { view in
            XCTAssertThrowsError(try view.find(text: "Thinking..."))
        }

        ViewHosting.host(view: sut)
        defer { ViewHosting.expel() }
        await fulfillment(of: [exp1, exp2, exp3], timeout: 5)
    }

    private func sseData(_ events: [String]) -> Data {
        Data(events.map { "data: \($0)\n\n" }.joined().utf8)
    }

    func testFullStreamEventSwitchRendersTokensToolBadgesAndActionPreview() async throws {
        MockURLProtocol.handlers["/api/ai/chat"] = (sseData([
            "{\"type\":\"tool_status\",\"tool\":\"search_channels\",\"status\":\"running\"}",
            "{\"type\":\"tool_call\",\"id\":\"call1\",\"tool\":\"search_channels\",\"arguments\":{}}",
            "{\"type\":\"token\",\"text\":\"Here \"}",
            "{\"type\":\"token\",\"text\":\"are your results.\"}",
            "{\"type\":\"tool_status\",\"tool\":\"search_channels\",\"status\":\"done\"}",
            "{\"type\":\"tool_result\",\"id\":\"call1\",\"content\":{\"count\":2}}",
            "{\"type\":\"action_preview\",\"action_id\":\"act1\",\"tool\":\"schedule_recording\",\"preview\":{\"channel\":\"4.1\"}}",
            "{\"type\":\"done\"}"
        ]), 200)
        let sut = iOSAIAssistantSheet(apiClient: makeAPIClient())
        let suggestion = try XCTUnwrap(AIChatHelpers.quickSuggestions.first)

        let exp1 = sut.inspection.inspect(after: 0) { view in
            try view.find(button: suggestion).tap()
        }
        let exp2 = sut.inspection.inspect(after: 0.5) { view in
            XCTAssertNoThrow(try view.find(text: "Here are your results."))
            XCTAssertNoThrow(try view.find(text: "search_channels"))
            XCTAssertNoThrow(try view.find(text: "Schedule Recording"))
            XCTAssertNoThrow(try view.find(text: "4.1"))
            XCTAssertNoThrow(try view.find(viewWithAccessibilityIdentifier: "ai-action-confirm-button"))
            XCTAssertNoThrow(try view.find(viewWithAccessibilityIdentifier: "ai-action-cancel-button"))
        }

        ViewHosting.host(view: sut)
        defer { ViewHosting.expel() }
        await fulfillment(of: [exp1, exp2], timeout: 3)
    }

    func testErrorEventSetsErrorText() async throws {
        MockURLProtocol.handlers["/api/ai/chat"] = (sseData([
            "{\"type\":\"error\",\"message\":\"Something went wrong\"}",
            "{\"type\":\"done\"}"
        ]), 200)
        let sut = iOSAIAssistantSheet(apiClient: makeAPIClient())
        let suggestion = try XCTUnwrap(AIChatHelpers.quickSuggestions.first)

        let exp1 = sut.inspection.inspect(after: 0) { view in
            try view.find(button: suggestion).tap()
        }
        let exp2 = sut.inspection.inspect(after: 0.5) { view in
            XCTAssertNoThrow(try view.find(text: "Something went wrong"))
        }

        ViewHosting.host(view: sut)
        defer { ViewHosting.expel() }
        await fulfillment(of: [exp1, exp2], timeout: 3)
    }

    private func hostViewWithPendingActionPreview(
        tool: String = "schedule_recording"
    ) -> iOSAIAssistantSheet {
        MockURLProtocol.handlers["/api/ai/chat"] = (sseData([
            "{\"type\":\"action_preview\",\"action_id\":\"act1\",\"tool\":\"\(tool)\",\"preview\":{\"channel\":\"4.1\"}}",
            "{\"type\":\"done\"}"
        ]), 200)
        return iOSAIAssistantSheet(apiClient: makeAPIClient())
    }

    func testConfirmActionSuccessRendersConfirmedState() async throws {
        MockURLProtocol.handlers["/api/ai/actions/act1/confirm"] = (Data("{\"result\":\"ok\"}".utf8), 200)
        let sut = hostViewWithPendingActionPreview()
        let suggestion = try XCTUnwrap(AIChatHelpers.quickSuggestions.first)

        let exp1 = sut.inspection.inspect(after: 0) { view in
            try view.find(button: suggestion).tap()
        }
        let exp2 = sut.inspection.inspect(after: 1.0) { view in
            try view.find(viewWithAccessibilityIdentifier: "ai-action-confirm-button").button().tap()
        }
        let exp3 = sut.inspection.inspect(after: 2.0) { view in
            XCTAssertNoThrow(try view.find(text: "Action confirmed and scheduled."))
        }

        ViewHosting.host(view: sut)
        defer { ViewHosting.expel() }
        await fulfillment(of: [exp1, exp2, exp3], timeout: 5)
    }

    func testConfirmActionFailureRendersFailedState() async throws {
        MockURLProtocol.handlers["/api/ai/actions/act1/confirm"] = (Data("{\"detail\":\"nope\"}".utf8), 500)
        let sut = hostViewWithPendingActionPreview()
        let suggestion = try XCTUnwrap(AIChatHelpers.quickSuggestions.first)

        let exp1 = sut.inspection.inspect(after: 0) { view in
            try view.find(button: suggestion).tap()
        }
        let exp2 = sut.inspection.inspect(after: 1.0) { view in
            try view.find(viewWithAccessibilityIdentifier: "ai-action-confirm-button").button().tap()
        }
        let exp3 = sut.inspection.inspect(after: 2.0) { view in
            XCTAssertNoThrow(try view.find(text: "Failed to execute action."))
        }

        ViewHosting.host(view: sut)
        defer { ViewHosting.expel() }
        await fulfillment(of: [exp1, exp2, exp3], timeout: 5)
    }

    func testCancelActionRendersCancelledState() async throws {
        MockURLProtocol.handlers["/api/ai/actions/act1/cancel"] = (Data("{\"ok\":true}".utf8), 200)
        let sut = hostViewWithPendingActionPreview()
        let suggestion = try XCTUnwrap(AIChatHelpers.quickSuggestions.first)

        let exp1 = sut.inspection.inspect(after: 0) { view in
            try view.find(button: suggestion).tap()
        }
        let exp2 = sut.inspection.inspect(after: 1.0) { view in
            try view.find(viewWithAccessibilityIdentifier: "ai-action-cancel-button").button().tap()
        }
        let exp3 = sut.inspection.inspect(after: 2.0) { view in
            XCTAssertNoThrow(try view.find(text: "Action cancelled."))
        }

        ViewHosting.host(view: sut)
        defer { ViewHosting.expel() }
        await fulfillment(of: [exp1, exp2, exp3], timeout: 5)
    }

    // MARK: - Tool-name humanization

    private func assertActionPreviewShowsHumanizedName(tool: String, expected: String) async throws {
        let sut = hostViewWithPendingActionPreview(tool: tool)
        let suggestion = try XCTUnwrap(AIChatHelpers.quickSuggestions.first)

        let exp1 = sut.inspection.inspect(after: 0) { view in
            try view.find(button: suggestion).tap()
        }
        let exp2 = sut.inspection.inspect(after: 0.5) { view in
            XCTAssertNoThrow(try view.find(text: expected), "Expected humanized name '\(expected)' for tool '\(tool)'")
        }

        ViewHosting.host(view: sut)
        defer { ViewHosting.expel() }
        await fulfillment(of: [exp1, exp2], timeout: 3)
    }

    func testHumanReadableToolNameScheduleRecording() async throws {
        try await assertActionPreviewShowsHumanizedName(tool: "schedule_recording", expected: "Schedule Recording")
    }

    func testHumanReadableToolNameCancelRecordingRule() async throws {
        try await assertActionPreviewShowsHumanizedName(tool: "cancel_recording_rule", expected: "Cancel Recording Rule")
    }

    func testHumanReadableToolNameDeleteRecording() async throws {
        try await assertActionPreviewShowsHumanizedName(tool: "delete_recording", expected: "Delete Recording")
    }

    func testHumanReadableToolNameFallsBackToCapitalizedUnderscoreReplacement() async throws {
        try await assertActionPreviewShowsHumanizedName(tool: "search_channels", expected: "Search Channels")
    }
}
