import Foundation

@MainActor
public final class WatchSessionManager: ObservableObject {
    @Published public private(set) var activeSessionId: String?
    @Published public private(set) var activeRecordingId: String?
    @Published public private(set) var isPromoted: Bool = false

    private let apiClient: APIClient
    private var heartbeatTask: Task<Void, Never>?

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func startWatch(channelNumber: String) async throws -> HDHomeRunRecording? {
        stopWatch()
        isPromoted = false

        let recording = try await apiClient.startWatch(channelNumber: channelNumber)
        if let sessionId = recording?.sessionId, let recId = recording?.recordingId {
            self.activeSessionId = sessionId
            self.activeRecordingId = recId
            startHeartbeat(sessionId: sessionId)
            Log.player.info("Started watch session \(sessionId) for channel \(channelNumber)")
        }
        return recording
    }

    private func startHeartbeat(sessionId: String) {
        heartbeatTask?.cancel()
        heartbeatTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 20_000_000_000) // 20s
                guard let self = self, !self.isPromoted else { break }
                do {
                    try await self.apiClient.heartbeatWatch(sessionId: sessionId)
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

        let recording = try await apiClient.promoteWatch(sessionId: sessionId, options: options)
        self.isPromoted = true
        heartbeatTask?.cancel()
        heartbeatTask = nil
        Log.player.info("Watch session \(sessionId) promoted to permanent DVR recording!")
        return recording
    }

    public func stopWatch() {
        heartbeatTask?.cancel()
        heartbeatTask = nil

        if let sessionId = activeSessionId, !isPromoted {
            let client = apiClient
            runWithBackgroundGrace(name: "StopWatchSession") {
                try? await client.stopWatch(sessionId: sessionId)
                Log.player.info("Stopped watch session \(sessionId)")
            }
        }

        activeSessionId = nil
        activeRecordingId = nil
        isPromoted = false
    }
}
