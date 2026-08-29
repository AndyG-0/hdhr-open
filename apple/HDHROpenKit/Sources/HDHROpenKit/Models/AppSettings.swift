import Foundation

public struct AppSettings: Codable, Sendable {
    public let timezone: String?
    public let guideProviderPriority: String?
    public let dvrServerPriority: String?

    enum CodingKeys: String, CodingKey {
        case timezone
        case guideProviderPriority = "guide_provider_priority"
        case dvrServerPriority = "dvr_server_priority"
    }

    public init(timezone: String? = nil, guideProviderPriority: String? = nil, dvrServerPriority: String? = nil) {
        self.timezone = timezone
        self.guideProviderPriority = guideProviderPriority
        self.dvrServerPriority = dvrServerPriority
    }
}

public struct HDHomeRunTranscodePreset: Identifiable, Codable, Sendable {
    public let id: String
    public let label: String
    public let description: String
    public let inputArgs: [String]
    public let outputArgs: [String]
    public let hardware: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case description
        case inputArgs = "input_args"
        case outputArgs = "output_args"
        case hardware
    }
}

public struct HWAccelDiagnostics: Codable, Sendable {
    public let device: String
    public let summary: [String]
    public let sampleError: String?

    enum CodingKeys: String, CodingKey {
        case device
        case summary
        case sampleError = "sample_error"
    }
}

public struct NetworkIntegration: Identifiable, Codable, Sendable {
    public let id: String
    public let type: String
    public let name: String
    public let settings: [String: AnyCodable]
}

public struct NetworkTestConnectionResult: Codable, Sendable {
    public let ok: Bool
    public let detail: String?
    public let error: String?
}

// AnyCodable helper for flexible JSON dictionaries
public struct AnyCodable: Codable, @unchecked Sendable {
    public let value: Any

    public init(_ value: Any) {
        self.value = value
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else {
            value = NSNull()
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let array as [Any]:
            try container.encode(array.map { AnyCodable($0) })
        case let dict as [String: Any]:
            try container.encode(dict.mapValues { AnyCodable($0) })
        default:
            try container.encodeNil()
        }
    }
}
