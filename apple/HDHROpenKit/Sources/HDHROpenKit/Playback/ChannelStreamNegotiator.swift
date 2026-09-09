import Foundation

/// What `ChannelStreamNegotiator.negotiate(_:)` produced. Pure data - applying
/// it (calling `PlayerEngine.loadMedia`, storing it on a view model / slot) is
/// the caller's job.
public struct StreamNegotiationResult: Sendable {
    public let streamURL: URL
    public let hlsSessionId: String
    public let watchSessionId: String?
    /// The `HDHomeRunRecording` produced by whichever tier succeeded - the
    /// watch-session recording when `isWatchSession` is true, or the
    /// unmanaged-capture recording metadata a direct channel HLS session may
    /// still return (`nil` if that direct session has no capture backing it).
    public let recording: HDHomeRunRecording?
    public let isWatchSession: Bool
    public let isLive: Bool
    public let isSeekable: Bool
}

/// What to negotiate a stream for.
public enum StreamNegotiationTarget: Sendable {
    case channel(HDHomeRunChannel)
    case recording(HDHomeRunRecording)
}

public enum StreamNegotiationError: LocalizedError, Sendable {
    case noPlayableURL
    case streamURLCreationFailed

    public var errorDescription: String? {
        switch self {
        case .noPlayableURL:
            "No playable URL for this recording."
        case .streamURLCreationFailed:
            "Could not build stream URL."
        }
    }
}

/// Negotiates a playable HLS session for a channel or recording, trying a
/// watch session (live pause/rewind) first and falling back to a direct HLS
/// session. This is the single place that logic lives - it used to be
/// duplicated (and drifted) across `PlayerViewModel.playChannel`/
/// `playRecording` and three call sites in `MultiPlayerViewModel`.
@MainActor
public final class ChannelStreamNegotiator {
    private let apiClient: APIClient
    private let watchSessionManager: WatchSessionManager

    public init(apiClient: APIClient, watchSessionManager: WatchSessionManager) {
        self.apiClient = apiClient
        self.watchSessionManager = watchSessionManager
    }

    public func negotiate(_ target: StreamNegotiationTarget) async throws -> StreamNegotiationResult {
        switch target {
        case let .channel(channel):
            try await negotiateChannel(channel)
        case let .recording(recording):
            try await negotiateRecording(recording)
        }
    }

    /// Tears down whatever `negotiate(_:)` produced. Safe to call on any
    /// result and idempotent from the caller's perspective (the underlying
    /// stop calls are themselves best-effort/fire-and-forget).
    public func teardown(_ result: StreamNegotiationResult) {
        let apiClient = apiClient
        let sessionId = result.hlsSessionId
        runWithBackgroundGrace(name: "StopHLSSession_\(sessionId)") {
            try? await apiClient.stopHLSSession(sessionId: sessionId)
        }
        if let watchSessionId = result.watchSessionId {
            watchSessionManager.stopSession(sessionId: watchSessionId)
        }
    }

    private func negotiateChannel(_ channel: HDHomeRunChannel) async throws -> StreamNegotiationResult {
        let baseURL = await apiClient.baseURL

        // 1. Try starting a watch session for live pause/rewind, packaged as HLS.
        do {
            if let watchRec = try await watchSessionManager.startSession(channelNumber: channel.channelNumber),
               let playUrl = watchRec.playUrl
            {
                let hlsSession = try await apiClient.createRecordingHLSSession(url: playUrl, recordingId: watchRec.recordingId)
                if let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: hlsSession.sessionId) {
                    Log.player
                        .info("Watch session HLS: sessionId=\(hlsSession.sessionId, privacy: .public) url=\(playlistURL.absoluteString, privacy: .public)")
                    return StreamNegotiationResult(
                        streamURL: playlistURL,
                        hlsSessionId: hlsSession.sessionId,
                        watchSessionId: watchRec.sessionId,
                        recording: watchRec,
                        isWatchSession: true,
                        isLive: true,
                        isSeekable: true
                    )
                }
                // Playlist URL couldn't be built - don't leak the watch
                // session we just started before falling back below.
                if let watchSessionId = watchRec.sessionId {
                    watchSessionManager.stopSession(sessionId: watchSessionId)
                }
            }
        } catch {
            Log.player.warning("Watch session auto-start failed, falling back to direct HLS stream: \(error.localizedDescription)")
        }

        // 2. Direct HLS streaming fallback (busy tuner / no watch session).
        let rec = try await apiClient.createChannelHLSSession(channelNumber: channel.channelNumber)
        guard let sessionId = rec.sessionId,
              let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: sessionId)
        else {
            throw StreamNegotiationError.streamURLCreationFailed
        }
        Log.player.info("Direct channel HLS: sessionId=\(sessionId, privacy: .public) url=\(playlistURL.absoluteString, privacy: .public)")
        return StreamNegotiationResult(
            streamURL: playlistURL,
            hlsSessionId: sessionId,
            watchSessionId: nil,
            recording: rec.recordingId != nil ? rec : nil,
            isWatchSession: false,
            isLive: true,
            isSeekable: false
        )
    }

    private func negotiateRecording(_ recording: HDHomeRunRecording) async throws -> StreamNegotiationResult {
        guard let playUrl = recording.playUrl, !playUrl.isEmpty else {
            throw StreamNegotiationError.noPlayableURL
        }
        let baseURL = await apiClient.baseURL
        let hlsSession = try await apiClient.createRecordingHLSSession(url: playUrl, recordingId: recording.recordingId)
        guard let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: hlsSession.sessionId) else {
            throw StreamNegotiationError.streamURLCreationFailed
        }
        Log.player.info("Recording HLS: sessionId=\(hlsSession.sessionId, privacy: .public) url=\(playlistURL.absoluteString, privacy: .public)")
        return StreamNegotiationResult(
            streamURL: playlistURL,
            hlsSessionId: hlsSession.sessionId,
            watchSessionId: nil,
            recording: recording,
            isWatchSession: false,
            isLive: recording.isInProgress,
            isSeekable: true
        )
    }
}
