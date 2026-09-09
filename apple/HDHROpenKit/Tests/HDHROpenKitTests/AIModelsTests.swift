import XCTest
@testable import HDHROpenKit

final class AIModelsTests: XCTestCase {
    func testEncodeChatRequest() throws {
        let wire = [
            AIChatWireMessage.user("What's on tonight?"),
            AIChatWireMessage.assistant("Let me check the guide.", toolCalls: [
                AIChatWireToolCall(id: "call_1", name: "search_guide", arguments: ["query": AnyCodable("sports")])
            ]),
            AIChatWireMessage.tool(id: "call_1", name: "search_guide", result: ["found": AnyCodable(2)])
        ]
        let context = AIChatContext(now: "2026-09-06T12:00:00Z", timezone: "America/Los_Angeles", selectedChannel: "5.1")
        let request = AIChatRequest(messages: wire, context: context)

        let data = try JSONEncoder().encode(request)
        let json = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])

        XCTAssertNotNil(json["messages"])
        XCTAssertNotNil(json["context"])

        let msgs = try XCTUnwrap(json["messages"] as? [[String: Any]])
        XCTAssertEqual(msgs.count, 3)
        XCTAssertEqual(msgs[0]["role"] as? String, "user")
        XCTAssertEqual(msgs[0]["content"] as? String, "What's on tonight?")
        XCTAssertEqual(msgs[1]["role"] as? String, "assistant")
        XCTAssertEqual(msgs[2]["role"] as? String, "tool")
        XCTAssertEqual(msgs[2]["tool_call_id"] as? String, "call_1")
    }

    func testDecodeStreamEvents() throws {
        let tokenJSON = """
        {"type": "token", "text": "Hello world"}
        """.data(using: .utf8)!
        let tokenEvent = try JSONDecoder().decode(AIStreamEvent.self, from: tokenJSON)
        XCTAssertEqual(tokenEvent.type, "token")
        XCTAssertEqual(tokenEvent.text, "Hello world")

        let toolCallJSON = """
        {"type": "tool_call", "id": "call_abc", "tool": "search_guide", "arguments": {"query": "news"}}
        """.data(using: .utf8)!
        let toolCallEvent = try JSONDecoder().decode(AIStreamEvent.self, from: toolCallJSON)
        XCTAssertEqual(toolCallEvent.type, "tool_call")
        XCTAssertEqual(toolCallEvent.id, "call_abc")
        XCTAssertEqual(toolCallEvent.tool, "search_guide")
        XCTAssertEqual(toolCallEvent.arguments?["query"]?.value as? String, "news")

        let actionPreviewJSON = """
        {
            "type": "action_preview",
            "action_id": "act_999",
            "tool": "schedule_recording",
            "preview": {"title": "Star Trek", "channel": "7.1"}
        }
        """.data(using: .utf8)!
        let actionPreviewEvent = try JSONDecoder().decode(AIStreamEvent.self, from: actionPreviewJSON)
        XCTAssertEqual(actionPreviewEvent.type, "action_preview")
        XCTAssertEqual(actionPreviewEvent.actionId, "act_999")
        XCTAssertEqual(actionPreviewEvent.tool, "schedule_recording")
        XCTAssertEqual(actionPreviewEvent.preview?["title"]?.value as? String, "Star Trek")

        let doneJSON = """
        {"type": "done"}
        """.data(using: .utf8)!
        let doneEvent = try JSONDecoder().decode(AIStreamEvent.self, from: doneJSON)
        XCTAssertEqual(doneEvent.type, "done")
    }

    func testToWireMessages() {
        let turns = [
            AIChatTurn(role: "user", text: "Record football"),
            AIChatTurn(
                role: "assistant",
                text: "I found NFL Football.",
                toolStatuses: [AIToolStatusEntry(tool: "search_guide", status: "done")],
                actionPreview: AIActionPreviewEntry(
                    actionId: "act_1",
                    tool: "schedule_recording",
                    preview: ["title": AnyCodable("NFL Football")]
                ),
                toolCalls: [
                    AIToolCallRecord(
                        id: "call_1",
                        name: "search_guide",
                        arguments: ["query": AnyCodable("football")],
                        result: ["count": AnyCodable(1)]
                    )
                ]
            )
        ]

        let wire = AIChatHelpers.toWireMessages(turns: turns)
        XCTAssertEqual(wire.count, 3)
        XCTAssertEqual(wire[0].role, "user")
        XCTAssertEqual(wire[0].content?.value as? String, "Record football")
        XCTAssertEqual(wire[1].role, "assistant")
        XCTAssertEqual(wire[1].toolCalls?.count, 1)
        XCTAssertEqual(wire[1].toolCalls?.first?.name, "search_guide")
        XCTAssertEqual(wire[2].role, "tool")
        XCTAssertEqual(wire[2].toolCallId, "call_1")
    }

    func testToWireMessagesPlainAssistantTurnWithoutResolvedToolCalls() {
        // No tool calls at all, and a tool call whose result hasn't come back yet -
        // both should fall into the resolvedCalls.isEmpty branch and emit a single
        // plain assistant message, not a tool_calls-carrying one.
        let turns = [
            AIChatTurn(role: "user", text: "What's on tonight?"),
            AIChatTurn(role: "assistant", text: "Here's tonight's lineup."),
            AIChatTurn(
                role: "assistant",
                text: "Let me look that up.",
                toolCalls: [AIToolCallRecord(id: "call_2", name: "search_guide", arguments: [:], result: nil)]
            )
        ]

        let wire = AIChatHelpers.toWireMessages(turns: turns)
        XCTAssertEqual(wire.count, 3)
        XCTAssertEqual(wire[1].role, "assistant")
        XCTAssertEqual(wire[1].content?.value as? String, "Here's tonight's lineup.")
        XCTAssertNil(wire[1].toolCalls)
        XCTAssertEqual(wire[2].role, "assistant")
        XCTAssertEqual(wire[2].content?.value as? String, "Let me look that up.")
        XCTAssertNil(wire[2].toolCalls)
    }

    func testMemberwiseInitializers() {
        let event = AIStreamEvent(
            type: "tool_status",
            text: "partial",
            id: "id_1",
            tool: "search_guide",
            status: "running",
            message: "Searching...",
            arguments: ["query": AnyCodable("news")],
            content: ["k": AnyCodable("v")],
            actionId: "act_1",
            preview: ["title": AnyCodable("Star Trek")]
        )
        XCTAssertEqual(event.type, "tool_status")
        XCTAssertEqual(event.text, "partial")
        XCTAssertEqual(event.id, "id_1")
        XCTAssertEqual(event.tool, "search_guide")
        XCTAssertEqual(event.status, "running")
        XCTAssertEqual(event.message, "Searching...")
        XCTAssertEqual(event.arguments?["query"]?.value as? String, "news")
        XCTAssertEqual(event.content?["k"]?.value as? String, "v")
        XCTAssertEqual(event.actionId, "act_1")
        XCTAssertEqual(event.preview?["title"]?.value as? String, "Star Trek")

        let confirmResponse = AIConfirmActionResponse(result: AnyCodable("ok"))
        XCTAssertEqual(confirmResponse.result?.value as? String, "ok")
        XCTAssertNil(AIConfirmActionResponse().result)

        let cancelResponse = AICancelActionResponse(ok: false)
        XCTAssertFalse(cancelResponse.ok)
        XCTAssertTrue(AICancelActionResponse().ok)

        let listModels = AIListModelsResponse(ok: true, models: ["gpt-4", "gpt-5"], error: nil)
        XCTAssertTrue(listModels.ok)
        XCTAssertEqual(listModels.models, ["gpt-4", "gpt-5"])
        XCTAssertNil(listModels.error)
        let listModelsError = AIListModelsResponse(ok: false, error: "unavailable")
        XCTAssertFalse(listModelsError.ok)
        XCTAssertEqual(listModelsError.models, [])
        XCTAssertEqual(listModelsError.error, "unavailable")

        let toolStatus = AIToolStatusEntry(tool: "search_guide", status: "error", message: "boom")
        XCTAssertEqual(toolStatus.id, "search_guide_error")
        XCTAssertEqual(toolStatus.message, "boom")

        let actionPreview = AIActionPreviewEntry(
            actionId: "act_2",
            tool: "schedule_recording",
            preview: ["title": AnyCodable("NFL")],
            resolution: .confirming
        )
        XCTAssertEqual(actionPreview.id, "act_2")
        XCTAssertEqual(actionPreview.resolution.rawValue, "confirming")
        XCTAssertEqual(AIActionPreviewEntry(actionId: "act_3", tool: "t", preview: [:]).resolution.rawValue, "pending")
    }
}
