import Foundation

@MainActor
public final class WatchSessionManager: ObservableObject {
    @Published public private(set) var activeSessionId: String?
    @Published public private(set) var activeRecordingId: String?
    @Published public private(set) var isPromoted = false

    private let apiClient: APIClient
    private var heartbeatTasks: [String: Task<Void, Never>] = [:]
    private var promotedSessions: Set<String> = []

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    // MARK: - Multi-Session API

    /// Set of session IDs with active heartbeat tasks.
    public var activeSessionIds: Set<String> {
        Set(heartbeatTasks.keys)
    }

    /// Number of concurrently active watch sessions.
    public var activeSessionCount: Int {
        heartbeatTasks.count
    }

    /// Whether a specific session ID is actively maintaining heartbeats.
    public func isSessionActive(_ sessionId: String) -> Bool {
        heartbeatTasks[sessionId] != nil
    }

    /// Starts an independent watch session without tearing down existing active sessions.
    public func startSession(channelNumber: String) async throws -> HDHomeRunRecording? {
        let recording = try await apiClient.startWatch(channelNumber: channelNumber)
        if let sessionId = recording?.sessionId {
            startHeartbeat(sessionId: sessionId)
            Log.player.info("Started watch session \(sessionId) for channel \(channelNumber)")
        }
        return recording
    }

    /// Stops a specific watch session, cancels its heartbeat task, and releases its tuner allocation.
    public func stopSession(sessionId: String) {
        heartbeatTasks[sessionId]?.cancel()
        heartbeatTasks.removeValue(forKey: sessionId)

        if !promotedSessions.contains(sessionId) {
            let client = apiClient
            runWithBackgroundGrace(name: "StopWatchSession_\(sessionId)") {
                try? await client.stopWatch(sessionId: sessionId)
                Log.player.info("Stopped watch session \(sessionId)")
            }
        } else {
            promotedSessions.remove(sessionId)
        }

        if activeSessionId == sessionId {
            activeSessionId = nil
            activeRecordingId = nil
            isPromoted = false
        }
    }

    /// Promotes a specific watch session to a permanent DVR recording, stopping its heartbeat.
    public func promoteSession(sessionId: String, options: [String: AnyCodable]? = nil) async throws -> HDHomeRunRecording {
        let recording = try await apiClient.promoteWatch(sessionId: sessionId, options: options)
        promotedSessions.insert(sessionId)
        heartbeatTasks[sessionId]?.cancel()
        heartbeatTasks.removeValue(forKey: sessionId)

        if activeSessionId == sessionId {
            isPromoted = true
        }

        Log.player.info("Watch session \(sessionId) promoted to permanent DVR recording!")
        return recording
    }

    /// Stops all actively tracked watch sessions.
    public func stopAll() {
        let sessionIds = Array(heartbeatTasks.keys)
        for sessionId in sessionIds {
            stopSession(sessionId: sessionId)
        }
        activeSessionId = nil
        activeRecordingId = nil
        isPromoted = false
    }

    // MARK: - Single-Session Backward Compatibility

    public func startWatch(channelNumber: String) async throws -> HDHomeRunRecording? {
        stopWatch()
        isPromoted = false

        let recording = try await startSession(channelNumber: channelNumber)
        if let sessionId = recording?.sessionId, let recId = recording?.recordingId {
            activeSessionId = sessionId
            activeRecordingId = recId
        }
        return recording
    }

    private func startHeartbeat(sessionId: String) {
        heartbeatTasks[sessionId]?.cancel()
        heartbeatTasks[sessionId] = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 20_000_000_000) // 20s
                guard let self, !self.promotedSessions.contains(sessionId) else { break }
                do {
                    try await apiClient.heartbeatWatch(sessionId: sessionId)
                    Log.player.debug("Heartbeat sent for watch session \(sessionId)")
                } catch {
                    Log.player.warning("Heartbeat failed for \(sessionId): \(error.localizedDescription)")
                }
            }
        }
    }

    public func promoteWatch(options: [String: AnyCodable]? = nil) async throws -> HDHomeRunRecording {
        guard let sessionId = activeSessionId else {
            throw APIError.noActiveWatchSession
        }
        return try await promoteSession(sessionId: sessionId, options: options)
    }

    public func stopWatch() {
        if let sessionId = activeSessionId {
            stopSession(sessionId: sessionId)
        }
        activeSessionId = nil
        activeRecordingId = nil
        isPromoted = false
    }
}
