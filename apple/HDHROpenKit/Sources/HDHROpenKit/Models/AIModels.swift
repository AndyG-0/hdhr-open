import Foundation

public struct AIChatWireToolCall: Codable, Sendable {
    public let id: String
    public let name: String
    public let arguments: [String: AnyCodable]

    public init(id: String, name: String, arguments: [String: AnyCodable] = [:]) {
        self.id = id
        self.name = name
        self.arguments = arguments
    }
}

public struct AIChatWireMessage: Codable, Sendable {
    public let role: String
    public let content: AnyCodable?
    public let toolCalls: [AIChatWireToolCall]?
    public let toolCallId: String?
    public let name: String?

    enum CodingKeys: String, CodingKey {
        case role
        case content
        case toolCalls = "tool_calls"
        case toolCallId = "tool_call_id"
        case name
    }

    public init(
        role: String,
        content: AnyCodable? = nil,
        toolCalls: [AIChatWireToolCall]? = nil,
        toolCallId: String? = nil,
        name: String? = nil
    ) {
        self.role = role
        self.content = content
        self.toolCalls = toolCalls
        self.toolCallId = toolCallId
        self.name = name
    }

    public static func user(_ text: String) -> AIChatWireMessage {
        AIChatWireMessage(role: "user", content: AnyCodable(text))
    }

    public static func assistant(_ text: String, toolCalls: [AIChatWireToolCall]? = nil) -> AIChatWireMessage {
        AIChatWireMessage(role: "assistant", content: AnyCodable(text), toolCalls: toolCalls)
    }

    public static func tool(id: String, name: String, result: [String: AnyCodable]) -> AIChatWireMessage {
        AIChatWireMessage(role: "tool", content: AnyCodable(result), toolCallId: id, name: name)
    }
}

public struct AIChatContext: Codable, Sendable, Equatable {
    public let now: String?
    public let timezone: String?
    public let selectedChannel: String?

    enum CodingKeys: String, CodingKey {
        case now
        case timezone
        case selectedChannel = "selected_channel"
    }

    public init(
        now: String? = ISO8601DateFormatter().string(from: Date()),
        timezone: String? = TimeZone.current.identifier,
        selectedChannel: String? = nil
    ) {
        self.now = now
        self.timezone = timezone
        self.selectedChannel = selectedChannel
    }
}

public struct AIChatRequest: Codable, Sendable {
    public let messages: [AIChatWireMessage]
    public let context: AIChatContext

    public init(messages: [AIChatWireMessage], context: AIChatContext = AIChatContext()) {
        self.messages = messages
        self.context = context
    }
}

public struct AIStreamEvent: Codable, Sendable {
    public let type: String
    public let text: String?
    public let id: String?
    public let tool: String?
    public let status: String?
    public let message: String?
    public let arguments: [String: AnyCodable]?
    public let content: [String: AnyCodable]?
    public let actionId: String?
    public let preview: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case type
        case text
        case id
        case tool
        case status
        case message
        case arguments
        case content
        case actionId = "action_id"
        case preview
    }

    public init(
        type: String,
        text: String? = nil,
        id: String? = nil,
        tool: String? = nil,
        status: String? = nil,
        message: String? = nil,
        arguments: [String: AnyCodable]? = nil,
        content: [String: AnyCodable]? = nil,
        actionId: String? = nil,
        preview: [String: AnyCodable]? = nil
    ) {
        self.type = type
        self.text = text
        self.id = id
        self.tool = tool
        self.status = status
        self.message = message
        self.arguments = arguments
        self.content = content
        self.actionId = actionId
        self.preview = preview
    }
}

public struct AIConfirmActionResponse: Codable, Sendable {
    public let result: AnyCodable?

    public init(result: AnyCodable? = nil) {
        self.result = result
    }
}

public struct AICancelActionResponse: Codable, Sendable {
    public let ok: Bool

    public init(ok: Bool = true) {
        self.ok = ok
    }
}

public struct AIListModelsResponse: Codable, Sendable {
    public let ok: Bool
    public let models: [String]
    public let error: String?

    public init(ok: Bool, models: [String] = [], error: String? = nil) {
        self.ok = ok
        self.models = models
        self.error = error
    }
}

// MARK: - Client View Models & State

public enum AIActionResolution: String, Sendable {
    case pending
    case confirming
    case confirmed
    case cancelled
    case failed
}

public struct AIToolStatusEntry: Identifiable, Sendable {
    public var id: String {
        "\(tool)_\(status)"
    }

    public let tool: String
    public var status: String // "running", "done", "error"
    public var message: String?

    public init(tool: String, status: String, message: String? = nil) {
        self.tool = tool
        self.status = status
        self.message = message
    }
}

public struct AIActionPreviewEntry: Identifiable, Sendable {
    public var id: String {
        actionId
    }

    public let actionId: String
    public let tool: String
    public let preview: [String: AnyCodable]
    public var resolution: AIActionResolution

    public init(
        actionId: String,
        tool: String,
        preview: [String: AnyCodable],
        resolution: AIActionResolution = .pending
    ) {
        self.actionId = actionId
        self.tool = tool
        self.preview = preview
        self.resolution = resolution
    }
}

public struct AIToolCallRecord: Identifiable, Sendable {
    public let id: String
    public let name: String
    public let arguments: [String: AnyCodable]
    public var result: [String: AnyCodable]?

    public init(
        id: String,
        name: String,
        arguments: [String: AnyCodable] = [:],
        result: [String: AnyCodable]? = nil
    ) {
        self.id = id
        self.name = name
        self.arguments = arguments
        self.result = result
    }
}

public struct AIChatTurn: Identifiable, Sendable {
    public let id: UUID
    public let role: String // "user" or "assistant"
    public var text: String
    public var toolStatuses: [AIToolStatusEntry]
    public var actionPreview: AIActionPreviewEntry?
    public var toolCalls: [AIToolCallRecord]

    public init(
        id: UUID = UUID(),
        role: String,
        text: String = "",
        toolStatuses: [AIToolStatusEntry] = [],
        actionPreview: AIActionPreviewEntry? = nil,
        toolCalls: [AIToolCallRecord] = []
    ) {
        self.id = id
        self.role = role
        self.text = text
        self.toolStatuses = toolStatuses
        self.actionPreview = actionPreview
        self.toolCalls = toolCalls
    }
}

public enum AIChatHelpers {
    public static let quickSuggestions = [
        "What's on tonight?",
        "Upcoming live sports",
        "What movies are playing today?",
        "Show my recording rules"
    ]

    public static func toWireMessages(turns: [AIChatTurn]) -> [AIChatWireMessage] {
        var wire: [AIChatWireMessage] = []
        for turn in turns {
            if turn.role == "user" {
                if !turn.text.isEmpty {
                    wire.append(.user(turn.text))
                }
                continue
            }

            let resolvedCalls = turn.toolCalls.filter { $0.result != nil }
            if resolvedCalls.isEmpty {
                if !turn.text.isEmpty {
                    wire.append(.assistant(turn.text))
                }
                continue
            }

            let wireCalls = resolvedCalls.map {
                AIChatWireToolCall(id: $0.id, name: $0.name, arguments: $0.arguments)
            }
            wire.append(.assistant(turn.text, toolCalls: wireCalls))

            for call in resolvedCalls {
                if let res = call.result {
                    wire.append(.tool(id: call.id, name: call.name, result: res))
                }
            }
        }
        return wire
    }
}
