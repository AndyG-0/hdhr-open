import Foundation

public struct SyncPlayPlaybackState: Codable, Sendable, Equatable {
    public let isPlaying: Bool
    public let position: Double
    public let playbackRate: Double
    public let updatedAt: Double?

    public init(
        isPlaying: Bool = false,
        position: Double = 0.0,
        playbackRate: Double = 1.0,
        updatedAt: Double? = nil
    ) {
        self.isPlaying = isPlaying
        self.position = position
        self.playbackRate = playbackRate
        self.updatedAt = updatedAt
    }

    enum CodingKeys: String, CodingKey {
        case isPlaying = "is_playing"
        case position
        case playbackRate = "playback_rate"
        case updatedAt = "updated_at"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.isPlaying = try container.decodeIfPresent(Bool.self, forKey: .isPlaying) ?? false
        self.position = try container.decodeIfPresent(Double.self, forKey: .position) ?? 0.0
        self.playbackRate = try container.decodeIfPresent(Double.self, forKey: .playbackRate) ?? 1.0
        self.updatedAt = try container.decodeIfPresent(Double.self, forKey: .updatedAt)
    }
}

public struct SyncPlayContent: Codable, Sendable, Equatable {
    public let type: String
    public let recordingId: String?
    public let channelNumber: String?
    public let title: String
    public let durationSeconds: Double?

    public init(
        type: String,
        recordingId: String? = nil,
        channelNumber: String? = nil,
        title: String? = nil,
        durationSeconds: Double? = nil
    ) {
        self.type = type
        self.recordingId = recordingId
        self.channelNumber = channelNumber
        self.title = title ?? ""
        self.durationSeconds = durationSeconds
    }

    enum CodingKeys: String, CodingKey {
        case type
        case recordingId = "recording_id"
        case channelNumber = "channel_number"
        case title
        case durationSeconds = "duration_seconds"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.type = try container.decode(String.self, forKey: .type)
        self.recordingId = try container.decodeIfPresent(String.self, forKey: .recordingId)
        self.channelNumber = try container.decodeIfPresent(String.self, forKey: .channelNumber)
        self.title = try container.decodeIfPresent(String.self, forKey: .title) ?? ""
        self.durationSeconds = try container.decodeIfPresent(Double.self, forKey: .durationSeconds)
    }
}

public struct SyncPlayParticipant: Codable, Sendable, Identifiable, Equatable {
    public var id: String { sessionId }
    public let sessionId: String
    public let userName: String
    public let isHost: Bool
    public let isReady: Bool
    public let position: Double
    public let pingMs: Double?

    public init(
        sessionId: String,
        userName: String,
        isHost: Bool = false,
        isReady: Bool = true,
        position: Double = 0.0,
        pingMs: Double? = nil
    ) {
        self.sessionId = sessionId
        self.userName = userName
        self.isHost = isHost
        self.isReady = isReady
        self.position = position
        self.pingMs = pingMs
    }

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case userName = "user_name"
        case isHost = "is_host"
        case isReady = "is_ready"
        case position
        case pingMs = "ping_ms"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.sessionId = try container.decode(String.self, forKey: .sessionId)
        self.userName = try container.decodeIfPresent(String.self, forKey: .userName) ?? "Viewer"
        self.isHost = try container.decodeIfPresent(Bool.self, forKey: .isHost) ?? false
        self.isReady = try container.decodeIfPresent(Bool.self, forKey: .isReady) ?? true
        self.position = try container.decodeIfPresent(Double.self, forKey: .position) ?? 0.0
        self.pingMs = try container.decodeIfPresent(Double.self, forKey: .pingMs)
    }
}

public struct SyncPlayRoom: Codable, Sendable, Equatable {
    public let roomCode: String
    public let hostSessionId: String
    public let createdAt: Double
    public let playbackState: SyncPlayPlaybackState
    public let currentContent: SyncPlayContent?
    public let participants: [SyncPlayParticipant]

    public init(
        roomCode: String,
        hostSessionId: String,
        createdAt: Double,
        playbackState: SyncPlayPlaybackState = SyncPlayPlaybackState(),
        currentContent: SyncPlayContent? = nil,
        participants: [SyncPlayParticipant] = []
    ) {
        self.roomCode = roomCode
        self.hostSessionId = hostSessionId
        self.createdAt = createdAt
        self.playbackState = playbackState
        self.currentContent = currentContent
        self.participants = participants
    }

    enum CodingKeys: String, CodingKey {
        case roomCode = "room_code"
        case hostSessionId = "host_session_id"
        case createdAt = "created_at"
        case playbackState = "playback_state"
        case currentContent = "current_content"
        case participants
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.roomCode = try container.decode(String.self, forKey: .roomCode)
        self.hostSessionId = try container.decodeIfPresent(String.self, forKey: .hostSessionId) ?? ""
        self.createdAt = try container.decodeIfPresent(Double.self, forKey: .createdAt) ?? 0.0
        self.playbackState = try container.decodeIfPresent(SyncPlayPlaybackState.self, forKey: .playbackState) ?? SyncPlayPlaybackState()
        self.currentContent = try container.decodeIfPresent(SyncPlayContent.self, forKey: .currentContent)
        self.participants = try container.decodeIfPresent([SyncPlayParticipant].self, forKey: .participants) ?? []
    }
}

public struct CreateSyncPlayRoomResponse: Codable, Sendable {
    public let room: SyncPlayRoom
    public let wsUrl: String?

    public init(room: SyncPlayRoom, wsUrl: String? = nil) {
        self.room = room
        self.wsUrl = wsUrl
    }

    enum CodingKeys: String, CodingKey {
        case room
        case wsUrl = "ws_url"
    }
}

public struct SyncPlayMessage: Codable, Sendable {
    public let type: String
    public let yourSessionId: String?
    public let room: SyncPlayRoom?
    public let participant: SyncPlayParticipant?
    public let sessionId: String?
    public let newHostSessionId: String?
    public let action: String?
    public let position: Double?
    public let playbackRate: Double?
    public let isPlaying: Bool?
    public let serverTime: Double?
    public let triggeredBy: String?
    public let content: SyncPlayContent?
    public let clientTime: Double?

    enum CodingKeys: String, CodingKey {
        case type
        case yourSessionId = "your_session_id"
        case room
        case participant
        case sessionId = "session_id"
        case newHostSessionId = "new_host_session_id"
        case action
        case position
        case playbackRate = "playback_rate"
        case isPlaying = "is_playing"
        case serverTime = "server_time"
        case triggeredBy = "triggered_by"
        case content
        case clientTime = "client_time"
    }
}
