import Combine
import Foundation

/// Owns the "what backend session is this player currently attached to"
/// concern for `PlayerViewModel`: negotiating a stream via
/// `ChannelStreamNegotiator`, tracking its ids, promoting a watch session to
/// a permanent recording, fetching/streaming a recording's metadata
/// (audio/video/transcode info, thumbnails, captions), and tearing
/// everything down. Pulled out of `PlayerViewModel` because that type had
/// grown session-negotiation, caption-alignment, and cross-device-sync
/// concerns all tangled together.
@MainActor
public final class StreamSessionCoordinator: ObservableObject {
    // `internal(set)` so `PlayerViewModel.activeHLSSessionId` can proxy
    // writes too - `selectAudioTrack`/`seekRecordingViaServer` swap the HLS
    // session out themselves (audio-track and server-seek concerns, not
    // session-negotiation ones, so they stay on `PlayerViewModel` untouched
    // by this extraction) and need to update it directly.
    @Published public internal(set) var activeHLSSessionId: String?
    @Published public private(set) var watchSessionId: String?
    @Published public private(set) var isWatchSession = false
    // `internal(set)` (not `private(set)`) so `PlayerViewModel.activeRecording`
    // can proxy both directions - tests seed it directly via
    // `@testable import` (see PlayerViewModelSeekResyncTests/
    // PlayerViewModelControlsAndMetadataTests), a pattern predating this
    // extraction that's preserved rather than churned.
    @Published public internal(set) var activeRecording: HDHomeRunRecording?
    @Published public private(set) var playbackMode: PlaybackMode?
    @Published public private(set) var thumbnailCues: [ThumbnailCue] = []
    @Published public private(set) var thumbnailSpriteURL: URL?
    @Published public private(set) var error: String?

    private let apiClient: APIClient
    private let watchSessionManager: WatchSessionManager
    private let negotiator: ChannelStreamNegotiator
    private var metadataTask: Task<Void, Never>?

    /// Bumped at the start of every `startChannel`/`startRecording` (and by
    /// `teardown()`), so a superseded call - one whose negotiation is still
    /// in flight when a newer `playChannel`/`playRecording`/`closePlayer()`
    /// call comes in - can detect it's stale once its `await` returns and
    /// tear down the backend session it just negotiated instead of either
    /// clobbering the newer call's state or leaking that session. Mirrors
    /// `MultiViewSlot.negotiationGeneration`'s per-slot guard in
    /// `MultiPlayerViewModel`, applied here at the single-player level.
    private var negotiationGeneration = 0

    public init(apiClient: APIClient, watchSessionManager: WatchSessionManager, negotiator: ChannelStreamNegotiator) {
        self.apiClient = apiClient
        self.watchSessionManager = watchSessionManager
        self.negotiator = negotiator
    }

    public func dismissError() {
        error = nil
    }

    public func startChannel(_ channel: HDHomeRunChannel, engine: PlayerEngine, autoplay: Bool = true) async {
        let myGeneration = negotiationGeneration + 1
        negotiationGeneration = myGeneration

        let result: StreamNegotiationResult
        do {
            result = try await negotiator.negotiate(.channel(channel))
        } catch {
            guard negotiationGeneration == myGeneration else { return }
            Log.player.error("Direct HLS channel stream failed: \(error.localizedDescription)")
            engine.setFailed(error.localizedDescription)
            return
        }
        guard negotiationGeneration == myGeneration else {
            negotiator.teardown(result)
            return
        }
        await apply(result, engine: engine, autoplay: autoplay)
        if let recording = activeRecording, recording.recordingId != nil {
            loadRecordingMetadata(recording)
        }
    }

    public func startRecording(_ recording: HDHomeRunRecording, engine: PlayerEngine, autoplay: Bool = true) async {
        let myGeneration = negotiationGeneration + 1
        negotiationGeneration = myGeneration

        let result: StreamNegotiationResult
        do {
            result = try await negotiator.negotiate(.recording(recording))
        } catch {
            guard negotiationGeneration == myGeneration else { return }
            Log.player.error("Recording HLS stream failed: \(error.localizedDescription)")
            engine.setFailed(error.localizedDescription)
            return
        }
        guard negotiationGeneration == myGeneration else {
            negotiator.teardown(result)
            return
        }
        await apply(result, engine: engine, autoplay: autoplay, initialDuration: recording.durationSeconds)
        loadRecordingMetadata(recording)
    }

    private func apply(_ result: StreamNegotiationResult, engine: PlayerEngine, autoplay: Bool, initialDuration: Double? = nil) async {
        activeHLSSessionId = result.hlsSessionId
        watchSessionId = result.watchSessionId
        isWatchSession = result.isWatchSession
        activeRecording = result.recording
        playbackMode = .serverTranscodedHls
        let headers = await hlsAuthHeaders()
        engine.loadMedia(
            url: result.streamURL,
            isLive: result.isLive,
            isSeekable: result.isSeekable,
            initialDuration: initialDuration,
            headers: headers,
            autoplay: autoplay
        )
    }

    /// Promotes the active watch session to a permanent DVR recording. Sets
    /// `error` on failure instead of only logging it, so the UI (which
    /// previously had no way to learn a promotion silently failed) can show it.
    public func promote(options: [String: AnyCodable]? = nil) async -> HDHomeRunRecording? {
        // `negotiate(_:)` starts watch sessions via `startSession(channelNumber:)`
        // (the multi-session API, not the single-session `startWatch` compat
        // wrapper), so promotion must target `watchSessionId` explicitly via
        // `promoteSession(sessionId:)` rather than the compat `promoteWatch()`,
        // which only knows about a session started through `startWatch`.
        guard isWatchSession, let watchSessionId else { return nil }
        do {
            let promoted = try await watchSessionManager.promoteSession(sessionId: watchSessionId, options: options)
            activeRecording = promoted
            Log.player.info("Promoted live watch to DVR recording: \(promoted.title)")
            return promoted
        } catch {
            Log.player.error("Failed to promote watch session: \(error.localizedDescription)")
            self.error = error.localizedDescription
            return nil
        }
    }

    /// Fetches recording detail (audio/video/transcode info) and thumbnail
    /// VTT, then starts caption polling if still in progress. Stored in a
    /// cancellable task (mirroring `PlayerViewModel.serverSeekTask`'s
    /// idiom) so `teardown()` can cancel it - previously this was a bare
    /// fire-and-forget `Task` that could complete after `closePlayer()` and
    /// repopulate `thumbnailCues`/`thumbnailSpriteURL` on an already-reset
    /// player engine.
    public func loadRecordingMetadata(_ recording: HDHomeRunRecording) {
        guard let recId = recording.recordingId, let playUrl = recording.playUrl else { return }

        metadataTask?.cancel()
        metadataTask = Task { [weak self] in
            guard let self else { return }
            let baseURL = await apiClient.baseURL
            if Task.isCancelled {
                return
            }

            if let detail = try? await apiClient.getRecordingDetail(url: playUrl, recordingId: recId, recordEnd: recording.recordEnd) {
                if Task.isCancelled {
                    return
                }
                onMetadataDetail?(detail)
            }

            if Task.isCancelled {
                return
            }
            if let vttURL = StreamURLBuilder.thumbnailVttURL(baseURL: baseURL, recordingId: recId, playUrl: playUrl, recordEnd: recording.recordEnd) {
                let spriteURL = StreamURLBuilder.thumbnailSpriteURL(baseURL: baseURL, recordingId: recId, playUrl: playUrl, recordEnd: recording.recordEnd)
                if Task.isCancelled {
                    return
                }
                thumbnailSpriteURL = spriteURL
                if let (data, _) = try? await URLSession.shared.data(from: vttURL),
                   let vttString = String(data: data, encoding: .utf8)
                {
                    if Task.isCancelled {
                        return
                    }
                    thumbnailCues = VTTParser.parseThumbnailVtt(from: vttString)
                }
            }

            if Task.isCancelled {
                return
            }
            await onCaptionsReady?(recording)
        }
    }

    /// Set by `PlayerViewModel` to apply audio/video/transcode/duration info
    /// onto its `playerEngine` - kept out of this type since `PlayerEngine`
    /// mutation for those fields lives on `PlayerViewModel` today.
    public var onMetadataDetail: ((HDHomeRunRecordingDetail) -> Void)?
    /// Set by `PlayerViewModel` to run its caption fetch-once + polling logic
    /// once metadata has loaded, since caption alignment stays owned by
    /// `PlayerViewModel` for now.
    public var onCaptionsReady: ((HDHomeRunRecording) async -> Void)?

    public func teardown() {
        // Invalidate any negotiation still in flight so it tears down its
        // session (once its `await` returns) instead of re-populating state
        // this teardown just cleared.
        negotiationGeneration += 1
        metadataTask?.cancel()
        metadataTask = nil
        // Mirrors `promote(options:)`'s reasoning: the watch session (if any)
        // was started via `startSession(channelNumber:)`, so it must be
        // stopped by id via `stopSession(sessionId:)` - the compat
        // `stopWatch()` only knows about a session started through `startWatch`.
        if let watchSessionId {
            watchSessionManager.stopSession(sessionId: watchSessionId)
        }
        if let sessionId = activeHLSSessionId {
            let apiClient = apiClient
            runWithBackgroundGrace(name: "StopHLSSession") {
                try? await apiClient.stopHLSSession(sessionId: sessionId)
            }
        }
        activeHLSSessionId = nil
        watchSessionId = nil
        isWatchSession = false
        activeRecording = nil
        playbackMode = nil
        thumbnailCues = []
        thumbnailSpriteURL = nil
    }

    private func hlsAuthHeaders() async -> [String: String] {
        guard let token = await apiClient.currentBearerToken() else { return [:] }
        return ["Authorization": "Bearer \(token)"]
    }
}
