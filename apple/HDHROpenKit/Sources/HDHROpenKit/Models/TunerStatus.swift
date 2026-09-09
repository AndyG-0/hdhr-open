import Foundation

public struct TunerViewerInfo: Codable, Sendable {
    public let userName: String
    public let clientIp: String?

    enum CodingKeys: String, CodingKey {
        case userName = "user_name"
        case clientIp = "client_ip"
    }
}

public struct TunerClientInfo: Codable, Sendable {
    public let type: String
    public let name: String
    public let ip: String?
    public let hostname: String?
    public let details: String?
    public let recordingId: String?
    public let scheduledId: String?
    public let isRecording: Bool
    public let viewers: [TunerViewerInfo]

    enum CodingKeys: String, CodingKey {
        case type
        case name
        case ip
        case hostname
        case details
        case recordingId = "recording_id"
        case scheduledId = "scheduled_id"
        case isRecording = "is_recording"
        case viewers
    }

    public init(
        type: String,
        name: String,
        ip: String? = nil,
        hostname: String? = nil,
        details: String? = nil,
        recordingId: String? = nil,
        scheduledId: String? = nil,
        isRecording: Bool = false,
        viewers: [TunerViewerInfo] = []
    ) {
        self.type = type
        self.name = name
        self.ip = ip
        self.hostname = hostname
        self.details = details
        self.recordingId = recordingId
        self.scheduledId = scheduledId
        self.isRecording = isRecording
        self.viewers = viewers
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        name = try container.decode(String.self, forKey: .name)
        ip = try container.decodeIfPresent(String.self, forKey: .ip)
        hostname = try container.decodeIfPresent(String.self, forKey: .hostname)
        details = try container.decodeIfPresent(String.self, forKey: .details)
        recordingId = try container.decodeIfPresent(String.self, forKey: .recordingId)
        scheduledId = try container.decodeIfPresent(String.self, forKey: .scheduledId)
        isRecording = try container.decodeIfPresent(Bool.self, forKey: .isRecording) ?? false
        viewers = try container.decodeIfPresent([TunerViewerInfo].self, forKey: .viewers) ?? []
    }
}

public struct TunerWarningInfo: Codable, Sendable {
    public let severity: String
    public let message: String
}

public struct HDHomeRunTuner: Identifiable, Codable, Sendable {
    public var id: Int {
        index
    }

    public let index: Int
    public let resource: String?
    public let inUse: Bool
    public let channelNumber: String?
    public let channelName: String?
    public let targetIp: String?
    public let client: TunerClientInfo?
    public let warning: TunerWarningInfo?
    public let signalStrengthPercent: Int?
    public let signalQualityPercent: Int?
    public let symbolQualityPercent: Int?
    public let networkRateBps: Int64?

    enum CodingKeys: String, CodingKey {
        case index
        case resource
        case inUse = "in_use"
        case channelNumber = "channel_number"
        case channelName = "channel_name"
        case targetIp = "target_ip"
        case client
        case warning
        case signalStrengthPercent = "signal_strength_percent"
        case signalQualityPercent = "signal_quality_percent"
        case symbolQualityPercent = "symbol_quality_percent"
        case networkRateBps = "network_rate_bps"
    }

    public var formattedRateMbps: String {
        guard let bps = networkRateBps, bps > 0 else { return "0.0 Mbps" }
        let mbps = Double(bps) / 1_000_000.0
        return String(format: "%.1f Mbps", mbps)
    }
}

public struct HDHomeRunTunerInfo: Codable, Sendable {
    public let friendlyName: String
    public let modelNumber: String?
    public let firmwareVersion: String?
    public let tunerCount: Int?

    enum CodingKeys: String, CodingKey {
        case friendlyName = "friendly_name"
        case modelNumber = "model_number"
        case firmwareVersion = "firmware_version"
        case tunerCount = "tuner_count"
    }
}

public struct HDHomeRunDvrInfo: Codable, Sendable {
    public let friendlyName: String
    public let version: String?
    public let freeSpaceBytes: Int64?
    public let isBuiltin: Bool?
    public let provider: String?

    enum CodingKeys: String, CodingKey {
        case friendlyName = "friendly_name"
        case version
        case freeSpaceBytes = "free_space_bytes"
        case isBuiltin = "is_builtin"
        case provider
    }

    public var formattedFreeSpace: String {
        guard let bytes = freeSpaceBytes, bytes > 0 else { return "Unknown" }
        let gb = Double(bytes) / 1_073_741_824.0
        if gb >= 1000.0 {
            let tb = gb / 1024.0
            return String(format: "%.2f TB free", tb)
        }
        return String(format: "%.1f GB free", gb)
    }
}
