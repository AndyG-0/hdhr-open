import Foundation

public struct HDHomeRunTuner: Identifiable, Codable, Sendable {
    public var id: Int { index }
    public let index: Int
    public let inUse: Bool
    public let channelNumber: String?
    public let channelName: String?
    public let signalStrengthPercent: Int?
    public let signalQualityPercent: Int?
    public let symbolQualityPercent: Int?
    public let networkRateBps: Int64?

    enum CodingKeys: String, CodingKey {
        case index
        case inUse = "in_use"
        case channelNumber = "channel_number"
        case channelName = "channel_name"
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
