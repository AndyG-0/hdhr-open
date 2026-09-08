import Combine
import Foundation

@MainActor
public final class SyncPlayClient: ObservableObject {
    @Published public private(set) var room: SyncPlayRoom?
    @Published public private(set) var participants: [SyncPlayParticipant] = []
    @Published public private(set) var sessionId: String?
    @Published public private(set) var isHost = false
    @Published public private(set) var pingMs = 0.0
    @Published public private(set) var isConnected = false

    public var onRemotePlay: ((Double, Double) -> Void)?
    public var onRemotePause: ((Double) -> Void)?
    public var onRemoteSeek: ((Double) -> Void)?
    public var onRemoteContentChange: ((SyncPlayContent) -> Void)?
    public var getCurrentPosition: (() -> Double)?
    public var isPlayerReady: (() -> Bool)?

    private var webSocketTask: URLSessionWebSocketTask?
    private var pingTimer: Task<Void, Never>?
    private var progressTimer: Task<Void, Never>?
    private let jsonDecoder = JSONDecoder()
    private let jsonEncoder = JSONEncoder()

    public init() {}

    public func connect(url: URL) {
        disconnect()

        let session = URLSession(configuration: .default)
        let task = session.webSocketTask(with: url)
        webSocketTask = task
        isConnected = true
        task.resume()

        receiveMessage()
        startHeartbeats()
        Log.network.info("SyncPlay WebSocket connected to \(url.absoluteString)")
    }

    public func disconnect() {
        sendJson(["type": "leave"])
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
        handleDisconnected()
    }

    private func handleDisconnected() {
        isConnected = false
        room = nil
        participants = []
        sessionId = nil
        isHost = false
        pingTimer?.cancel()
        pingTimer = nil
        progressTimer?.cancel()
        progressTimer = nil
    }

    private func receiveMessage() {
        guard let task = webSocketTask else { return }
        task.receive { [weak self] result in
            Task { @MainActor in
                guard let self, self.isConnected else { return }
                switch result {
                case let .success(message):
                    switch message {
                    case let .string(text):
                        self.handleRawMessage(text)
                    case let .data(data):
                        if let text = String(data: data, encoding: .utf8) {
                            self.handleRawMessage(text)
                        }
                    @unknown default:
                        break
                    }
                    self.receiveMessage()
                case let .failure(error):
                    Log.network.error("SyncPlay WebSocket receive error: \(error.localizedDescription)")
                    self.handleDisconnected()
                }
            }
        }
    }

    public func handleRawMessage(_ text: String) {
        guard let data = text.data(using: .utf8) else { return }
        do {
            let msg = try jsonDecoder.decode(SyncPlayMessage.self, from: data)
            handleParsedMessage(msg)
        } catch {
            Log.network.error("SyncPlay JSON decode error: \(error.localizedDescription)")
        }
    }

    private func handleParsedMessage(_ msg: SyncPlayMessage) {
        switch msg.type {
        case "room_state":
            if let r = msg.room {
                room = r
                participants = r.participants
                if let sid = msg.yourSessionId {
                    sessionId = sid
                    isHost = (r.hostSessionId == sid)
                }
            }
        case "participant_joined":
            if let p = msg.participant {
                if !participants.contains(where: { $0.sessionId == p.sessionId }) {
                    participants.append(p)
                }
            }
        case "participant_left":
            if let leftId = msg.sessionId {
                participants.removeAll(where: { $0.sessionId == leftId })
                if let newHostId = msg.newHostSessionId {
                    isHost = (sessionId == newHostId)
                    participants = participants.map {
                        SyncPlayParticipant(
                            sessionId: $0.sessionId,
                            userName: $0.userName,
                            isHost: $0.sessionId == newHostId,
                            isReady: $0.isReady,
                            position: $0.position,
                            pingMs: $0.pingMs
                        )
                    }
                }
            }
        case "participant_updated":
            if let updated = msg.participant {
                participants = participants.map {
                    $0.sessionId == updated.sessionId ? updated : $0
                }
            }
        case "playback_update":
            let action = msg.action
            let pos = msg.position ?? 0.0
            let rate = msg.playbackRate ?? 1.0
            let isPlaying = msg.isPlaying ?? false
            let serverTime = msg.serverTime

            if let currentRoom = room {
                let newState = SyncPlayPlaybackState(
                    isPlaying: isPlaying,
                    position: pos,
                    playbackRate: rate,
                    updatedAt: serverTime
                )
                room = SyncPlayRoom(
                    roomCode: currentRoom.roomCode,
                    hostSessionId: currentRoom.hostSessionId,
                    createdAt: currentRoom.createdAt,
                    playbackState: newState,
                    currentContent: currentRoom.currentContent,
                    participants: participants
                )
            }

            if msg.triggeredBy != sessionId {
                switch action {
                case "play":
                    onRemotePlay?(pos, rate)
                case "pause":
                    onRemotePause?(pos)
                case "seek":
                    onRemoteSeek?(pos)
                default:
                    break
                }
            }
        case "content_changed":
            if let content = msg.content {
                onRemoteContentChange?(content)
            }
            if let r = msg.room {
                room = r
                participants = r.participants
            }
        case "host_changed":
            if let newHostId = msg.newHostSessionId {
                isHost = (sessionId == newHostId)
                participants = participants.map {
                    SyncPlayParticipant(
                        sessionId: $0.sessionId,
                        userName: $0.userName,
                        isHost: $0.sessionId == newHostId,
                        isReady: $0.isReady,
                        position: $0.position,
                        pingMs: $0.pingMs
                    )
                }
            }
        case "pong":
            if let clientTime = msg.clientTime {
                let now = Date().timeIntervalSince1970 * 1000.0
                let rtt = max(1.0, now - clientTime)
                pingMs = rtt
            }
        default:
            break
        }
    }

    private func startHeartbeats() {
        pingTimer?.cancel()
        pingTimer = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                guard let self, isConnected else { break }
                let now = Date().timeIntervalSince1970 * 1000.0
                sendJson(["type": "ping", "client_time": now])
            }
        }

        progressTimer?.cancel()
        progressTimer = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                guard let self, isConnected else { break }
                let pos = getCurrentPosition?() ?? 0.0
                let ready = isPlayerReady?() ?? true
                sendJson([
                    "type": "progress",
                    "position": pos,
                    "is_ready": ready,
                    "ping_ms": pingMs
                ])
            }
        }
    }

    public func sendPlay(position: Double, playbackRate: Double = 1.0) {
        sendJson([
            "type": "play",
            "position": position,
            "playback_rate": playbackRate
        ])
    }

    public func sendPause(position: Double) {
        sendJson([
            "type": "pause",
            "position": position
        ])
    }

    public func sendSeek(position: Double) {
        sendJson([
            "type": "seek",
            "position": position
        ])
    }

    public func changeContent(_ content: SyncPlayContent) {
        do {
            let contentData = try jsonEncoder.encode(content)
            if let contentStr = String(data: contentData, encoding: .utf8) {
                sendJson([
                    "type": "change_content",
                    "content": contentStr
                ])
            }
        } catch {
            Log.network.error("Error encoding content for SyncPlay: \(error.localizedDescription)")
        }
    }

    public func transferHost(targetSessionId: String) {
        sendJson([
            "type": "transfer_host",
            "target_session_id": targetSessionId
        ])
    }

    private func sendJson(_ dict: [String: Any]) {
        guard let task = webSocketTask else { return }
        do {
            let data = try JSONSerialization.data(withJSONObject: dict, options: [])
            if let str = String(data: data, encoding: .utf8) {
                task.send(.string(str)) { error in
                    if let err = error {
                        Log.network.error("SyncPlay send error: \(err.localizedDescription)")
                    }
                }
            }
        } catch {
            Log.network.error("SyncPlay JSON serialize error: \(error.localizedDescription)")
        }
    }
}
