import Combine
import Foundation

/// How the current session is being delivered - set by PlayerViewModel at
/// each stream-URL-construction call site, since PlayerEngine has no way to
/// infer this from the URL alone. Apple platforms have no direct-play path
/// today (AVFoundation can't decode raw MPEG-2/MPEG-TS), so `.direct` is
/// unused here for now, but the type keeps the UI identical in shape to
/// Android's, which does use it.
public enum PlaybackMode: Sendable {
    case direct
    case serverTranscodedHls
}

/// The full internal auto-quality ladder, including `.minimal` - a rung the
/// manual `VideoQuality` picker never offers directly but the auto poll can
/// still step down to. Mirrors Android's `AutoTier`/`AUTO_TIER_ORDER` and the
/// web player's `TIER_TARGET_MBPS` ladder; values must stay numerically
/// identical across all three clients. Declared without `private` (like
/// `PlayerViewModel.lastRawCues` et al.) so `@testable import` test code can
/// seed `PlayerViewModel.autoEffectiveTier` and drive `sampleAutoQualityTick()`
/// directly, mirroring Android's `PlayerViewModelQualityTest`.
enum AutoTier: Sendable {
    case minimal
    case low
    case medium
    case high

    var backendValue: String {
        switch self {
        case .minimal: "minimal"
        case .low: "low"
        case .medium: "medium"
        case .high: "high"
        }
    }

    var targetMbps: Double {
        switch self {
        case .minimal: 0.7
        case .low: 1.5
        case .medium: 3.0
        case .high: 5.0
        }
    }

    var maxSourceHeight: Int? {
        switch self {
        case .minimal: 360
        case .low: 480
        case .medium: 720
        case .high: nil
        }
    }
}

private let autoTierOrder: [AutoTier] = [.minimal, .low, .medium, .high]

private extension VideoQuality {
    /// The auto-tier a manual selection corresponds to - `.auto` itself maps
    /// to `.high` since that's where the auto poll always starts a fresh
    /// session before it has any samples to judge.
    var autoTier: AutoTier {
        switch self {
        case .low: .low
        case .medium: .medium
        case .high, .auto: .high
        }
    }
}

/// Trims the ladder to tiers that would actually look different for a given
/// source resolution - mirrors Android's `effectiveAutoTierOrder`/web's
/// `effectiveTierOrder`. A source already at or below a tier's cap wouldn't
/// visibly upscale by landing on it, so those tiers collapse into `.minimal`.
private func effectiveAutoTierOrder(sourceHeight: Int?) -> [AutoTier] {
    guard let sourceHeight, sourceHeight > 0 else { return autoTierOrder }
    let ladder = autoTierOrder.filter { tier in
        guard let cap = tier.maxSourceHeight else { return true }
        return cap < sourceHeight
    }
    return ladder.isEmpty ? [.minimal] : ladder
}

private func stepDown(_ tier: AutoTier, ladder: [AutoTier]) -> AutoTier? {
    guard let idx = autoTierOrder.firstIndex(of: tier) else { return nil }
    for i in stride(from: idx - 1, through: 0, by: -1) where ladder.contains(autoTierOrder[i]) {
        return autoTierOrder[i]
    }
    return nil
}

private func stepUp(_ tier: AutoTier, ladder: [AutoTier]) -> AutoTier? {
    guard let idx = autoTierOrder.firstIndex(of: tier) else { return nil }
    for i in (idx + 1)..<autoTierOrder.count where ladder.contains(autoTierOrder[i]) {
        return autoTierOrder[i]
    }
    return nil
}

/// Picks the highest tier in `ladder` whose target is still within reach of
/// `avgMbps` (after the downgrade margin), for landing on a tier once a
/// downgrade has already been justified by a stall or buffer-drain signal -
/// never the trigger for a downgrade itself. Mirrors Android's/web's
/// `bestTierForSpeed`.
private func bestTierForSpeed(_ avgMbps: Double, ladder: [AutoTier], downgradeMargin: Double) -> AutoTier {
    var best = ladder.first ?? .minimal
    for tier in ladder where avgMbps >= tier.targetMbps * downgradeMargin {
        best = tier
    }
    return best
}

@MainActor
public final class PlayerViewModel: ObservableObject {
    public let playerEngine: PlayerEngine
    public let captionController: CaptionController
    public let watchSessionManager: WatchSessionManager
    public let sessionCoordinator: StreamSessionCoordinator

    @Published public private(set) var activeChannel: HDHomeRunChannel?
    @Published public private(set) var activeAiring: HDHomeRunGuideEntry?

    /// `activeRecording`/`isWatchSession`/`activeHLSSessionId`/`playbackMode`/
    /// `thumbnailCues`/`thumbnailSpriteURL`/`error` are now owned by
    /// `sessionCoordinator`; these forward to it so the public API (and every
    /// existing view/test that reads `playerViewModel.<x>`) is unchanged.
    /// `objectWillChange` forwarding (below, in `init`) makes them reactive
    /// despite not being `@Published` themselves.
    public internal(set) var activeRecording: HDHomeRunRecording? {
        get { sessionCoordinator.activeRecording }
        set { sessionCoordinator.activeRecording = newValue }
    }

    public var isWatchSession: Bool {
        sessionCoordinator.isWatchSession
    }

    public internal(set) var activeHLSSessionId: String? {
        get { sessionCoordinator.activeHLSSessionId }
        set { sessionCoordinator.activeHLSSessionId = newValue }
    }

    public var playbackMode: PlaybackMode? {
        sessionCoordinator.playbackMode
    }

    public var thumbnailCues: [ThumbnailCue] {
        sessionCoordinator.thumbnailCues
    }

    public var thumbnailSpriteURL: URL? {
        sessionCoordinator.thumbnailSpriteURL
    }

    public var error: String? {
        sessionCoordinator.error
    }

    public func dismissError() {
        sessionCoordinator.dismissError()
    }

    @Published public private(set) var isPromoting = false
    @Published public private(set) var isPromoted = false
    @Published public private(set) var isSwitchingAudioTrack = false
    @Published public private(set) var quality: VideoQuality = .auto
    @Published public private(set) var isSwitchingQuality = false
    @Published public var showAudioMenu = false
    @Published public var showSettingsOverlay = false
    @Published public var showChannelSwitcher = false
    @Published public var showRecordMenu = false
    @Published public var showSyncPlaySheet = false
    @Published public var showSharePlaySheet = false

    public let syncPlayClient: SyncPlayClient
    public let sharePlayCoordinator: SharePlayCoordinator
    public let playbackPreferences: PlaybackPreferences

    @Published public private(set) var autoSkipPulse: Date?

    /// Guards auto-skip to at most once per segment. Compared against the
    /// active segment's startSeconds rather than reset on a timer, so it
    /// survives seekRecordingViaServer()'s reload and is only cleared by
    /// closePlayer() when a genuinely new recording/channel loads.
    private var lastAutoSkippedSegmentStart: Double?

    private let apiClient: APIClient
    private var cancellables = Set<AnyCancellable>()

    // Live caption polling/alignment state (CC-7). Declared without
    // `private` (rather than Android's reflection-based test access) so
    // `@testable import` test code can seed and inspect it directly.
    static let captionPollIntervalNanos: UInt64 = 1_500_000_000 // 1.5s, mirrors Android's CAPTION_POLL_INTERVAL_MS
    static let liveCueStretchSeconds = 4.0 // mirrors Android's LIVE_CUE_STRETCH_SECONDS
    // Caps how far behind "now" a stretched cue's slot can be pushed by a
    // burst of backlog (see alignLiveCues's cursor-reset comment for why
    // this exists - mirrors web's caption-controller.ts LIVE_CUE_MAX_
    // CATCHUP_SECONDS from the CC-13 freeze fix). Past this cap, further
    // backlog cues are left unstretched (naturally expired, dropped from
    // display) instead of extending the queue arbitrarily far forward.
    static let liveCueMaxCatchupSeconds = 20.0
    var lastRawCues: [CaptionCue] = []
    var stretchedCueDisplay: [String: (start: Double, end: Double)] = [:]
    var nextStretchSlotAbsolute = 0.0
    private var captionPollTask: Task<Void, Never>?

    // Auto-quality constants (CC-12 parity fix) - must stay numerically
    // identical to HDHomeRunPlayer.svelte and Android's PlayerViewModel.kt.
    private static let stallWindowSeconds = 20.0
    private static let stallThreshold = 2
    private static let throughputSampleIntervalNanos: UInt64 = 5_000_000_000
    private static let downgradeSampleCount = 3
    private static let upgradeSampleCount = 12
    private static let downgradeMargin = 1.2
    private static let upgradeMargin = 1.5
    private static let baselineSampleCount = 24
    private static let baselineDropRatio = 0.5
    private static let baselineNearTargetRatio = 0.8
    private static let bufferTrendSampleCount = 4
    private static let bufferSafeFloorSeconds = 10.0
    private static let bufferDrainDropSeconds = 3.0

    /// The tier the auto poll has actually landed on - tracked separately
    /// from `quality` so AUTO can silently step down to `.minimal` without
    /// changing the user-visible "Auto" selection. Mirrors Android's
    /// `autoEffectiveTier`.
    // autoEffectiveTier/stallTimestamps/speedSamplesMbps/bufferedAheadSamples
    // declared without `private` (see AutoTier's doc comment above) so tests
    // can seed them directly.
    var autoEffectiveTier: AutoTier = .high
    private var autoQualityPollTask: Task<Void, Never>?
    var stallTimestamps: [Date] = []
    var speedSamplesMbps: [Double] = []
    var bufferedAheadSamples: [Double] = []

    public init(apiClient: APIClient, watchSessionManager: WatchSessionManager, playbackPreferences: PlaybackPreferences? = nil) {
        self.apiClient = apiClient
        self.watchSessionManager = watchSessionManager
        self.playbackPreferences = playbackPreferences ?? PlaybackPreferences()
        playerEngine = PlayerEngine()
        captionController = CaptionController()
        syncPlayClient = SyncPlayClient()
        sharePlayCoordinator = SharePlayCoordinator()
        let negotiator = ChannelStreamNegotiator(apiClient: apiClient, watchSessionManager: watchSessionManager)
        sessionCoordinator = StreamSessionCoordinator(apiClient: apiClient, watchSessionManager: watchSessionManager, negotiator: negotiator)
        quality = self.playbackPreferences.videoQuality
        autoEffectiveTier = quality.autoTier

        // Forward sessionCoordinator changes - views only observe
        // `playerViewModel`, so its nested @Published state needs relaying
        // the same way playerEngine/syncPlayClient/sharePlayCoordinator are below.
        sessionCoordinator.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        sessionCoordinator.onMetadataDetail = { [weak self] detail in
            guard let self else { return }
            playerEngine.setAudioTracks(detail.audio)
            playerEngine.setVideoSpecs(detail.video)
            playerEngine.setTranscodeInfo(detail.transcode)
            playerEngine.setCommercialSegments(detail.commercialSegments)
            if let dur = detail.durationSeconds, dur > 0 {
                playerEngine.setDuration(dur)
            }
        }

        sessionCoordinator.onCaptionsReady = { [weak self] recording in
            guard let self else { return }
            await fetchCaptionsOnce(recording: recording)
            startCaptionPolling(recording: recording)
        }

        // Sync player engine time with captions
        playerEngine.$currentTime
            .sink { [weak self] time in
                self?.captionController.updatePlaybackTime(time)
            }
            .store(in: &cancellables)

        // Reactive stall path (CC-12 parity fix): 2 stalls within a rolling
        // 20s window triggers an immediate one-tier downgrade, independent
        // of the proactive buffer-drain poll below. Mirrors Android's
        // collection of PlayerEngine.stallPulse and the web player's
        // recordStallAndMaybeDowngrade().
        playerEngine.$stallPulse
            .compactMap { $0 }
            .sink { [weak self] pulse in
                guard let self, quality == .auto else { return }
                stallTimestamps.append(pulse)
                stallTimestamps.removeAll { pulse.timeIntervalSince($0) > Self.stallWindowSeconds }
                if stallTimestamps.count >= Self.stallThreshold {
                    stallTimestamps.removeAll()
                    applyAutoDowngradeOneTier()
                }
            }
            .store(in: &cancellables)

        // Auto-skip commercials, when enabled, firing at most once per
        // segment via lastAutoSkippedSegmentStart. activeCommercialSegment
        // is a computed property on playerEngine with no publisher of its
        // own, so it's re-derived here from its two inputs.
        Publishers.CombineLatest(playerEngine.$currentTime, playerEngine.$commercialSegments)
            .sink { [weak self] time, segments in
                guard let self else { return }
                guard let segment = segments.first(where: { time >= $0.startSeconds && time < $0.endSeconds }) else { return }
                guard self.playbackPreferences.autoSkipCommercialsEnabled,
                      lastAutoSkippedSegmentStart != segment.startSeconds
                else { return }
                lastAutoSkippedSegmentStart = segment.startSeconds
                // Not skipActiveCommercial(): that re-reads playerEngine.currentTime,
                // but @Published fires in willSet, before the backing storage is
                // actually updated - at this point it's still the pre-seek value, so
                // activeCommercialSegment would see a stale currentTime and no-op.
                seek(to: segment.endSeconds)
                autoSkipPulse = Date()
            }
            .store(in: &cancellables)

        // Views only observe `playerViewModel` (via @EnvironmentObject), not
        // `playerEngine` directly - as a nested ObservableObject, playerEngine's
        // own @Published changes (state, currentTime, etc.) don't propagate to
        // those views unless forwarded here.
        playerEngine.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        // Forward syncPlayClient changes
        syncPlayClient.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        syncPlayClient.getCurrentPosition = { [weak self] in
            self?.playerEngine.currentTime ?? 0.0
        }

        syncPlayClient.isPlayerReady = { [weak self] in
            guard let self else { return false }
            return playerEngine.state == .playing || playerEngine.state == .paused
        }

        syncPlayClient.onRemotePlay = { [weak self] pos, _ in
            guard let self else { return }
            let diff = abs(playerEngine.currentTime - pos)
            if diff > 2.0 {
                playerEngine.seek(to: pos)
            }
            playerEngine.play()
        }

        syncPlayClient.onRemotePause = { [weak self] pos in
            guard let self else { return }
            playerEngine.pause()
            let diff = abs(playerEngine.currentTime - pos)
            if diff > 0.5 {
                playerEngine.seek(to: pos)
            }
        }

        syncPlayClient.onRemoteSeek = { [weak self] pos in
            guard let self else { return }
            playerEngine.seek(to: pos)
        }

        syncPlayClient.onRemoteContentChange = { [weak self] content in
            Task { @MainActor [weak self] in
                self?.handleRemoteContentChange(content)
            }
        }

        // Forward sharePlayCoordinator changes
        sharePlayCoordinator.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }
            .store(in: &cancellables)

        sharePlayCoordinator.onSessionAvailable = { [weak self] session in
            self?.playerEngine.coordinateWithGroupSession(session)
        }

        sharePlayCoordinator.onRemoteContentChange = { [weak self] content in
            Task { @MainActor [weak self] in
                self?.handleRemoteContentChange(content)
            }
        }
    }

    public var isPlaying: Bool {
        playerEngine.state == .playing
    }

    /// Whether either cross-device watch-party transport (SyncPlay or
    /// SharePlay) is currently running. Both independently drive
    /// `playerEngine.play/pause/seek/loadMedia` with no cross-suppression,
    /// so they can't run simultaneously - UI trigger buttons and every
    /// session-start call site gate on this to enforce that.
    public var isCrossDeviceSyncActive: Bool {
        syncPlayClient.isConnected || sharePlayCoordinator.isSessionActive
    }

    public var mediaTitle: String {
        if let rec = activeRecording {
            return rec.title
        }
        if let ch = activeChannel {
            if let airing = activeAiring {
                return "\(ch.channelNumber) \(airing.title)"
            }
            return "\(ch.channelNumber) \(ch.name)"
        }
        return "Live TV"
    }

    /// Human-readable "how is this being played" line for the playback info
    /// panel, shared so iOS and tvOS render identical text.
    public var playbackModeLabel: String {
        switch playbackMode {
        case .direct:
            return "Direct (client-side)"
        case .serverTranscodedHls:
            if let presetLabel = playerEngine.transcodeInfo?.presetLabel {
                let hw = playerEngine.transcodeInfo?.hardware == true ? " (HW)" : ""
                return "Server transcoded via \(presetLabel)\(hw)"
            }
            return "Server transcoded (HLS)"
        case nil:
            return "Unknown"
        }
    }

    public var mediaSubtitle: String? {
        if let rec = activeRecording {
            if let ep = rec.episodeTitle, let des = rec.episodeDesignation {
                return "\(des) • \(ep)"
            }
            return rec.episodeTitle ?? rec.episodeDesignation ?? rec.channelName
        }
        if let airing = activeAiring {
            if let ep = airing.episodeTitle, let num = airing.episodeNumber {
                return "\(num) • \(ep)"
            }
            return airing.episodeTitle ?? airing.synopsis
        }
        return activeChannel?.name
    }

    public func playChannel(channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry? = nil) async {
        closePlayer()
        initializeQualityForNewSession()
        activeChannel = channel
        activeAiring = airing ?? channel.now
        playerEngine.setLoading()

        let syncContent = SyncPlayContent(
            type: "channel",
            channelNumber: channel.channelNumber,
            title: airing?.title ?? channel.name
        )
        if syncPlayClient.isConnected, syncPlayClient.isHost {
            syncPlayClient.changeContent(syncContent)
        }
        if sharePlayCoordinator.isSessionActive {
            sharePlayCoordinator.sendContentChange(syncContent)
        }

        await sessionCoordinator.startChannel(channel, engine: playerEngine, quality: autoEffectiveTier.backendValue)
        maybeStartAutoQualityPolling()
    }

    public func playRecording(_ recording: HDHomeRunRecording) async {
        closePlayer()
        initializeQualityForNewSession()
        activeChannel = nil
        activeAiring = nil
        // Set optimistically, before negotiation, so SyncPlay/SharePlay
        // "now playing" state and observers reflect the requested recording
        // even if the HLS session negotiation below fails.
        activeRecording = recording
        playerEngine.setLoading()

        let syncContent = SyncPlayContent(
            type: "recording",
            recordingId: recording.recordingId,
            channelNumber: recording.channelNumber,
            title: recording.title,
            durationSeconds: recording.durationSeconds
        )
        if syncPlayClient.isConnected, syncPlayClient.isHost {
            syncPlayClient.changeContent(syncContent)
        }
        if sharePlayCoordinator.isSessionActive {
            sharePlayCoordinator.sendContentChange(syncContent)
        }

        await sessionCoordinator.startRecording(recording, engine: playerEngine, quality: autoEffectiveTier.backendValue)
        maybeStartAutoQualityPolling()
    }

    public func promoteToRecording() async {
        guard isWatchSession, !isPromoting else { return }
        isPromoting = true
        defer { isPromoting = false }

        if await sessionCoordinator.promote() != nil {
            isPromoted = true
        }
    }

    /// Audio track selection is baked into the HLS packaging itself
    /// (backend maps a specific source audio stream via ffmpeg's `-map`
    /// when building the session) rather than exposed as switchable
    /// `AVMediaSelectionOption`s on the produced stream, so "switching"
    /// requires starting a new HLS session with the new audio index and
    /// resuming playback at the current position.
    public func selectAudioTrack(_ track: HDHomeRunRecordingAudioInfo) async {
        guard !isSwitchingAudioTrack, track.index != playerEngine.currentAudioTrack?.index else { return }

        isSwitchingAudioTrack = true
        defer { isSwitchingAudioTrack = false }

        let resumeTime = playerEngine.currentTime
        let isLive = playerEngine.isLive
        let isSeekable = playerEngine.isSeekable
        let previousSessionId = activeHLSSessionId
        let previousAudioTracks = playerEngine.availableAudioTracks
        let previousVideoSpecs = playerEngine.videoSpecs
        let previousTranscodeInfo = playerEngine.transcodeInfo
        let baseURL = await apiClient.baseURL

        do {
            let sessionId: String
            if let recording = activeRecording, let playUrl = recording.playUrl, !playUrl.isEmpty {
                let hlsSession = try await apiClient.createRecordingHLSSession(
                    url: playUrl,
                    recordingId: recording.recordingId,
                    start: resumeTime,
                    audioIndex: track.index,
                    provider: recording.provider
                )
                sessionId = hlsSession.sessionId
            } else if let channel = activeChannel {
                let rec = try await apiClient.createChannelHLSSession(channelNumber: channel.channelNumber, audioIndex: track.index)
                guard let recSessionId = rec.sessionId else {
                    Log.player.error("Audio track switch failed: no session id for channel HLS.")
                    return
                }
                sessionId = recSessionId
            } else {
                return
            }

            guard let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: sessionId) else {
                Log.player.error("Audio track switch failed: could not build stream URL.")
                return
            }
            Log.player.info("Audio track switch: sessionId=\(sessionId, privacy: .public) audioIndex=\(track.index)")
            activeHLSSessionId = sessionId
            // loadMedia() calls reset() internally, which wipes the audio
            // track list/video specs - restore them with the selected track atomically.
            await playerEngine.loadMedia(url: playlistURL, isLive: isLive, isSeekable: isSeekable, headers: hlsAuthHeaders())
            playerEngine.setAudioTracks(previousAudioTracks, selectedTrack: track)
            playerEngine.setVideoSpecs(previousVideoSpecs)
            playerEngine.setTranscodeInfo(previousTranscodeInfo)

            if let previousSessionId {
                let apiClient = apiClient
                runWithBackgroundGrace(name: "StopHLSSession") {
                    try? await apiClient.stopHLSSession(sessionId: previousSessionId)
                }
            }
        } catch {
            Log.player.error("Audio track switch failed: \(error.localizedDescription)")
        }
    }

    private func hlsAuthHeaders() async -> [String: String] {
        guard let token = await apiClient.currentBearerToken() else { return [:] }
        return ["Authorization": "Bearer \(token)"]
    }

    /// Resets quality state for a freshly-loaded session (new channel or
    /// recording) back to the persisted default preference, mirroring
    /// Android's `initializeQualityForNewSession()`. Called from
    /// `playChannel`/`playRecording` right after `closePlayer()`.
    private func initializeQualityForNewSession() {
        stopAutoQualityPolling()
        quality = playbackPreferences.videoQuality
        autoEffectiveTier = quality.autoTier
    }

    /// Starts the auto-quality poll if the just-negotiated session actually
    /// succeeded (an `activeHLSSessionId` was set) and the user's preference
    /// is AUTO. Called after `sessionCoordinator.startChannel`/`startRecording`
    /// returns, success or failure alike.
    private func maybeStartAutoQualityPolling() {
        guard quality == .auto, activeHLSSessionId != nil else { return }
        startAutoQualityPolling()
    }

    private func startAutoQualityPolling() {
        guard playbackMode == .serverTranscodedHls else { return }
        guard autoQualityPollTask == nil else { return }
        resetAutoQualitySamples()
        autoQualityPollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: Self.throughputSampleIntervalNanos)
                guard let self, quality == .auto else { break }
                await sampleAutoQualityTick()
            }
        }
    }

    private func stopAutoQualityPolling() {
        autoQualityPollTask?.cancel()
        autoQualityPollTask = nil
    }

    private func resetAutoQualitySamples() {
        speedSamplesMbps.removeAll()
        bufferedAheadSamples.removeAll()
        stallTimestamps.removeAll()
    }

    /// True only once a full window of buffered-ahead samples is collected
    /// AND the newest sample is below the safety floor AND it has shrunk by
    /// at least `bufferDrainDropSeconds` since the oldest sample in the
    /// window - a one-off wobble in an otherwise-healthy buffer is not a
    /// signal. Mirrors Android's `isBufferDraining()`/web's `isBufferDraining()`.
    private func isBufferDraining() -> Bool {
        guard bufferedAheadSamples.count >= Self.bufferTrendSampleCount,
              let newest = bufferedAheadSamples.last,
              let oldest = bufferedAheadSamples.first
        else { return false }
        return newest < Self.bufferSafeFloorSeconds && (oldest - newest) >= Self.bufferDrainDropSeconds
    }

    /// The core auto-quality gate, polled every 5s while `quality == .auto`.
    /// Buffer-drain is the necessary gate for any throughput-triggered
    /// downgrade - measured speed alone only picks *which* tier to land on
    /// once a stall or buffer-drain has already justified a downgrade.
    /// Mirrors Android's `sampleAutoQualityTick()`/web's `sampleThroughput()`.
    func sampleAutoQualityTick() async {
        if let bufferedAhead = playerEngine.bufferedAheadSeconds() {
            bufferedAheadSamples.append(bufferedAhead)
            while bufferedAheadSamples.count > Self.bufferTrendSampleCount {
                bufferedAheadSamples.removeFirst()
            }
        }

        guard let observedBitrate = playerEngine.observedBitrate else { return }
        let speedMbps = observedBitrate / 1_000_000.0
        speedSamplesMbps.append(speedMbps)
        while speedSamplesMbps.count > Self.baselineSampleCount {
            speedSamplesMbps.removeFirst()
        }

        let ladder = effectiveAutoTierOrder(sourceHeight: playerEngine.videoSpecs?.height)
        let tier = autoEffectiveTier

        let recentWindow = speedSamplesMbps.suffix(Self.downgradeSampleCount)
        if recentWindow.count >= Self.downgradeSampleCount, isBufferDraining() {
            let recentAvg = recentWindow.reduce(0, +) / Double(recentWindow.count)
            let baselineAvg = speedSamplesMbps.reduce(0, +) / Double(speedSamplesMbps.count)
            let baselineNearTarget = baselineAvg >= tier.targetMbps * Self.baselineNearTargetRatio

            if baselineNearTarget {
                if recentAvg < tier.targetMbps * Self.downgradeMargin {
                    let target = bestTierForSpeed(recentAvg, ladder: ladder, downgradeMargin: Self.downgradeMargin)
                    if let targetIdx = autoTierOrder.firstIndex(of: target),
                       let tierIdx = autoTierOrder.firstIndex(of: tier),
                       targetIdx < tierIdx
                    {
                        await applyAutoAdjustment(target)
                        return
                    }
                }
            } else if recentAvg < baselineAvg * Self.baselineDropRatio {
                if let target = stepDown(tier, ladder: ladder) {
                    await applyAutoAdjustment(target)
                    return
                }
            }
        }

        guard let nextUp = stepUp(tier, ladder: ladder) else { return }
        let upgradeWindow = speedSamplesMbps.suffix(Self.upgradeSampleCount)
        guard upgradeWindow.count >= Self.upgradeSampleCount, stallTimestamps.isEmpty else { return }
        let upgradeAvg = upgradeWindow.reduce(0, +) / Double(upgradeWindow.count)
        guard upgradeAvg >= nextUp.targetMbps * Self.upgradeMargin else { return }
        await applyAutoAdjustment(nextUp)
    }

    /// Fires a single one-tier downgrade from the reactive stall path, which
    /// runs synchronously from a Combine sink - spawns its own `Task` to
    /// reach the async `switchToQuality`, mirroring Android's
    /// `applyAutoDowngradeOneTier()` (launched fire-and-forget there too).
    private func applyAutoDowngradeOneTier() {
        let ladder = effectiveAutoTierOrder(sourceHeight: playerEngine.videoSpecs?.height)
        guard let target = stepDown(autoEffectiveTier, ladder: ladder) else { return }
        Task { [weak self] in
            await self?.applyAutoAdjustment(target)
        }
    }

    private func applyAutoAdjustment(_ target: AutoTier) async {
        autoEffectiveTier = target
        resetAutoQualitySamples()
        await switchToQuality(target.backendValue)
    }

    /// Manual quality selection from the picker UI. Mirrors Android's
    /// `selectQuality(preference:)`: switching to AUTO restarts at `.high`
    /// and resumes polling; switching to an explicit tier stops polling and
    /// locks onto that tier until AUTO is chosen again.
    public func selectQuality(_ newQuality: VideoQuality) async {
        guard newQuality != quality else { return }
        quality = newQuality
        playbackPreferences.videoQuality = newQuality
        if newQuality == .auto {
            autoEffectiveTier = .high
            await switchToQuality(AutoTier.high.backendValue)
            startAutoQualityPolling()
        } else {
            stopAutoQualityPolling()
            autoEffectiveTier = newQuality.autoTier
            await switchToQuality(newQuality.backendValue)
        }
    }

    /// Requests a new HLS session at `backendValue`'s quality tier and swaps
    /// to it in place, following `selectAudioTrack(_:)`'s exact
    /// capture/restart-session/loadMedia/restore/stop-old-session pattern.
    private func switchToQuality(_ backendValue: String?) async {
        guard !isSwitchingQuality else { return }
        isSwitchingQuality = true
        defer { isSwitchingQuality = false }

        let resumeTime = playerEngine.currentTime
        let isLive = playerEngine.isLive
        let isSeekable = playerEngine.isSeekable
        let previousSessionId = activeHLSSessionId
        let previousAudioTracks = playerEngine.availableAudioTracks
        let previousTrack = playerEngine.currentAudioTrack
        let previousVideoSpecs = playerEngine.videoSpecs
        let previousTranscodeInfo = playerEngine.transcodeInfo
        let baseURL = await apiClient.baseURL

        do {
            let sessionId: String
            if let recording = activeRecording, let playUrl = recording.playUrl, !playUrl.isEmpty {
                let hlsSession = try await apiClient.createRecordingHLSSession(
                    url: playUrl,
                    recordingId: recording.recordingId,
                    start: resumeTime,
                    audioIndex: previousTrack?.index,
                    provider: recording.provider,
                    quality: backendValue
                )
                sessionId = hlsSession.sessionId
            } else if let channel = activeChannel {
                let rec = try await apiClient.createChannelHLSSession(channelNumber: channel.channelNumber, audioIndex: previousTrack?.index, quality: backendValue)
                guard let recSessionId = rec.sessionId else {
                    Log.player.error("Quality switch failed: no session id for channel HLS.")
                    return
                }
                sessionId = recSessionId
            } else {
                return
            }

            guard let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: sessionId) else {
                Log.player.error("Quality switch failed: could not build stream URL.")
                return
            }
            Log.player.info("Quality switch: sessionId=\(sessionId, privacy: .public) quality=\(backendValue ?? "nil", privacy: .public)")
            activeHLSSessionId = sessionId
            await playerEngine.loadMedia(url: playlistURL, isLive: isLive, isSeekable: isSeekable, headers: hlsAuthHeaders())
            playerEngine.setAudioTracks(previousAudioTracks, selectedTrack: previousTrack)
            playerEngine.setVideoSpecs(previousVideoSpecs)
            playerEngine.setTranscodeInfo(previousTranscodeInfo)

            if let previousSessionId {
                let apiClient = apiClient
                runWithBackgroundGrace(name: "StopHLSSession") {
                    try? await apiClient.stopHLSSession(sessionId: previousSessionId)
                }
            }
        } catch {
            Log.player.error("Quality switch failed: \(error.localizedDescription)")
        }
    }

    /// Fetches and parses the caption VTT once, then aligns/stretches it
    /// against the player's current clock before publishing it to
    /// `captionController`. Best-effort: captions may not be extracted yet
    /// for an in-progress recording, so any failure here is swallowed - a
    /// poller (if running) retries on the next tick.
    private func fetchCaptionsOnce(recording: HDHomeRunRecording) async {
        guard let recId = recording.recordingId, let playUrl = recording.playUrl else { return }
        let baseURL = await apiClient.baseURL
        guard let capURL = StreamURLBuilder.captionsURL(baseURL: baseURL, recordingId: recId, playUrl: playUrl, recordEnd: recording.recordEnd) else { return }
        guard let (data, _) = try? await URLSession.shared.data(from: capURL),
              let vttString = String(data: data, encoding: .utf8) else { return }
        let cues = VTTParser.parseCaptions(from: vttString)
        lastRawCues = cues
        captionController.setCues(alignLiveCues(recording: recording, cues: cues))
    }

    /// Re-fetches captions every `captionPollIntervalNanos` while `recording`
    /// is in progress, so live captions keep appearing as CC extraction
    /// catches up. No-ops for an already-finished recording. Always does one
    /// more fetch right after the recording transitions out of "in
    /// progress" to pick up the final complete VTT before stopping.
    private func startCaptionPolling(recording: HDHomeRunRecording) {
        guard recording.isInProgress else { return }
        captionPollTask?.cancel()
        captionPollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: Self.captionPollIntervalNanos)
                guard let self, let current = activeRecording else { break }
                let wasInProgress = current.isInProgress
                await fetchCaptionsOnce(recording: current)
                if !wasInProgress {
                    break
                }
            }
        }
    }

    /// Remaps raw cue timestamps (anchored to the capture's absolute
    /// wall-clock start) onto the player's own rolling-live-window clock,
    /// and "stretches" any cue whose natural shifted end has already passed
    /// the current player time into a synthetic display window - CC
    /// extraction lag routinely runs well past a cue's own few-second
    /// window, so without this such cues would never satisfy
    /// `CaptionCue.contains` and would silently never display. Recomputed
    /// fresh on every call (not cached) since `baseOffsetSeconds` shifts as
    /// the live HLS window grows; only the per-cue stretch *decision* is
    /// memoized (keyed by cue id, which is stable across re-fetches) so a
    /// re-poll or re-seek reuses the same synthetic window instead of
    /// flickering it. VOD/finished recordings pass through untouched.
    private func alignLiveCues(recording: HDHomeRunRecording, cues: [CaptionCue]) -> [CaptionCue] {
        guard recording.isInProgress, let start = recording.start else { return cues }

        let elapsedCaptureSeconds = Date().timeIntervalSince1970 - start
        let playerTime = playerEngine.currentTime
        let baseOffsetSeconds = elapsedCaptureSeconds - playerTime

        // Re-anchor to "now" on every call instead of trusting wherever a
        // previous, separate call left the cursor. Without this, the cursor
        // advances by liveCueStretchSeconds per newly-stretched cue - slower
        // than real cue cadence (~2.85s avg observed) - so it drifts further
        // ahead of real time on every poll and never catches back up, pinning
        // near the cap below and queuing every cue after that behind an
        // unreachable backlog: a permanent freeze, not a bounded lag. Same
        // bug and fix as web's caption-controller.ts (CC-13).
        nextStretchSlotAbsolute = elapsedCaptureSeconds

        return cues.compactMap { cue in
            let window: (start: Double, end: Double)
            if let stretched = stretchedCueDisplay[cue.id] {
                window = stretched
            } else {
                let naturalEnd = cue.end - baseOffsetSeconds
                if naturalEnd > playerTime {
                    window = (cue.start, cue.end)
                } else {
                    let slotStart = max(cue.start, max(nextStretchSlotAbsolute, elapsedCaptureSeconds))
                    if slotStart - elapsedCaptureSeconds > Self.liveCueMaxCatchupSeconds {
                        window = (cue.start, cue.end)
                    } else {
                        let slotEnd = slotStart + Self.liveCueStretchSeconds
                        stretchedCueDisplay[cue.id] = (slotStart, slotEnd)
                        nextStretchSlotAbsolute = slotEnd
                        window = (slotStart, slotEnd)
                    }
                }
            }
            let displayEnd = window.end - baseOffsetSeconds
            guard displayEnd > 0 else { return nil }
            let displayStart = max(0, window.start - baseOffsetSeconds)
            return CaptionCue(start: displayStart, end: displayEnd, text: cue.text)
        }
    }

    public func play() {
        playerEngine.play()
        if syncPlayClient.isConnected {
            syncPlayClient.sendPlay(position: playerEngine.currentTime)
        }
    }

    public func pause() {
        playerEngine.pause()
        if syncPlayClient.isConnected {
            syncPlayClient.sendPause(position: playerEngine.currentTime)
        }
    }

    public func togglePlayPause() {
        if playerEngine.state == .playing {
            pause()
        } else {
            play()
        }
    }

    private var serverSeekTask: Task<Void, Never>?

    public func seek(to seconds: Double) {
        let clamped = max(0, min(seconds, playerEngine.duration > 0 ? playerEngine.duration : seconds))
        if let recording = activeRecording, let playUrl = recording.playUrl, !playUrl.isEmpty,
           !playerEngine.isPositionInSeekableRange(clamped)
        {
            seekRecordingViaServer(recording: recording, playUrl: playUrl, targetSeconds: clamped)
        } else {
            playerEngine.seek(to: clamped)
        }
        resyncCaptionsAfterSeek()
        if syncPlayClient.isConnected {
            syncPlayClient.sendSeek(position: clamped)
        }
    }

    private func seekRecordingViaServer(recording: HDHomeRunRecording, playUrl: String, targetSeconds: Double) {
        serverSeekTask?.cancel()

        let previousSessionId = activeHLSSessionId
        let previousAudioTracks = playerEngine.availableAudioTracks
        let previousTrack = playerEngine.currentAudioTrack
        let previousVideoSpecs = playerEngine.videoSpecs
        let previousTranscodeInfo = playerEngine.transcodeInfo
        let previousCommercialSegments = playerEngine.commercialSegments
        let totalDuration = playerEngine.duration > 0 ? playerEngine.duration : (recording.durationSeconds ?? 0)
        let isLive = recording.isInProgress
        let isSeekable = playerEngine.isSeekable

        // Update position and pause playback without seeking the out-of-range old item
        playerEngine.prepareForServerSeek(to: targetSeconds)

        serverSeekTask = Task { @MainActor [weak self] in
            guard let self else { return }

            let baseURL = await apiClient.baseURL
            do {
                let hlsSession = try await apiClient.createRecordingHLSSession(
                    url: playUrl,
                    recordingId: recording.recordingId,
                    start: targetSeconds,
                    audioIndex: previousTrack?.index,
                    provider: recording.provider
                )
                if Task.isCancelled {
                    let apiClient = apiClient
                    runWithBackgroundGrace(name: "StopCancelledHLSSession") {
                        try? await apiClient.stopHLSSession(sessionId: hlsSession.sessionId)
                    }
                    return
                }
                guard let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: hlsSession.sessionId) else {
                    return
                }
                activeHLSSessionId = hlsSession.sessionId
                await playerEngine.loadMedia(
                    url: playlistURL,
                    isLive: isLive,
                    isSeekable: isSeekable,
                    initialDuration: totalDuration,
                    initialTimeOffset: targetSeconds,
                    headers: hlsAuthHeaders()
                )
                playerEngine.setAudioTracks(previousAudioTracks, selectedTrack: previousTrack)
                playerEngine.setVideoSpecs(previousVideoSpecs)
                playerEngine.setTranscodeInfo(previousTranscodeInfo)
                playerEngine.setCommercialSegments(previousCommercialSegments)

                if let previousSessionId {
                    let apiClient = apiClient
                    runWithBackgroundGrace(name: "StopHLSSession") {
                        try? await apiClient.stopHLSSession(sessionId: previousSessionId)
                    }
                }
            } catch {
                if !Task.isCancelled {
                    Log.player.error("Server seek failed: \(error.localizedDescription)")
                }
            }
        }
    }

    public func skipForward(seconds: Double = 10.0) {
        let target = playerEngine.currentTime + seconds
        seek(to: target)
    }

    public func skipBackward(seconds: Double = 10.0) {
        let target = max(0, playerEngine.currentTime - seconds)
        seek(to: target)
    }

    public func skipActiveCommercial() {
        guard let segment = playerEngine.activeCommercialSegment else { return }
        seek(to: segment.endSeconds)
    }

    public func createSyncPlayRoom(userName: String) async throws -> SyncPlayRoom {
        guard !sharePlayCoordinator.isSessionActive else { throw APIError.crossDeviceSyncActive }
        let content = currentSyncPlayContent()
        let resp = try await apiClient.createSyncPlayRoom(userName: userName, initialContent: content)
        if let wsUrl = await apiClient.syncPlayWsUrl(roomCode: resp.room.roomCode, userName: userName) {
            syncPlayClient.connect(url: wsUrl)
        }
        return resp.room
    }

    public func joinSyncPlayRoom(roomCode: String, userName: String) async throws {
        guard !sharePlayCoordinator.isSessionActive else { throw APIError.crossDeviceSyncActive }
        guard let wsUrl = await apiClient.syncPlayWsUrl(roomCode: roomCode, userName: userName) else {
            throw APIError.invalidURL
        }
        syncPlayClient.connect(url: wsUrl)
    }

    public func leaveSyncPlayRoom() {
        syncPlayClient.disconnect()
    }

    public func transferSyncPlayHost(targetSessionId: String) {
        syncPlayClient.transferHost(targetSessionId: targetSessionId)
    }

    /// tvOS SharePlay entry point - no `GroupActivitySharingController`
    /// exists there, so this activates the shared activity directly (see
    /// `SharePlayCoordinator.activateOnTV(content:)`). No-op (rather than
    /// throwing) when there's nothing playing or SyncPlay already owns
    /// cross-device sync, matching the SyncPlay button's own visibility gate.
    public func startSharePlayOnTV() async {
        guard !syncPlayClient.isConnected, let content = currentSyncPlayContent() else { return }
        do {
            try await sharePlayCoordinator.activateOnTV(content: content)
        } catch {
            Log.player.error("SharePlay activation failed: \(error.localizedDescription, privacy: .public)")
        }
    }

    public func leaveSharePlaySession() {
        sharePlayCoordinator.leaveSession()
    }

    public func currentSyncPlayContent() -> SyncPlayContent? {
        if let rec = activeRecording {
            return SyncPlayContent(
                type: "recording",
                recordingId: rec.recordingId,
                channelNumber: rec.channelNumber,
                title: rec.title,
                durationSeconds: playerEngine.duration > 0 ? playerEngine.duration : rec.durationSeconds
            )
        }
        if let ch = activeChannel {
            return SyncPlayContent(
                type: "channel",
                channelNumber: ch.channelNumber,
                title: activeAiring?.title ?? ch.name
            )
        }
        return nil
    }

    /// Re-runs cue alignment against `lastRawCues` immediately after a
    /// seek/skip, instead of waiting for the next poll tick (which could be
    /// up to `captionPollIntervalNanos` away). No network call - the
    /// underlying VTT content hasn't changed, only the player's position.
    /// No-op for a finished/VOD recording, whose cue timestamps are static.
    /// Deliberately does not touch `stretchedCueDisplay`:
    /// `alignLiveCues` recomputes display coordinates fresh on every call
    /// from stretch windows stored in absolute time, so there's no stale
    /// state to clear. Clearing it here would be actively harmful - since
    /// each poll re-fetches and re-parses the *entire* caption history
    /// (full replace, not incremental), clearing the map would make every
    /// already-stretched cue in `lastRawCues` look "newly arrived"
    /// simultaneously, replaying the whole caption history in back-to-back
    /// stretch slots right after a seek.
    private func resyncCaptionsAfterSeek() {
        guard let recording = activeRecording, recording.isInProgress else { return }
        captionController.setCues(alignLiveCues(recording: recording, cues: lastRawCues))
    }

    private func resetCueStretch() {
        stretchedCueDisplay.removeAll()
        nextStretchSlotAbsolute = 0.0
        lastRawCues = []
    }

    public func closePlayer() {
        serverSeekTask?.cancel()
        serverSeekTask = nil
        playerEngine.reset()
        captionPollTask?.cancel()
        captionPollTask = nil
        resetCueStretch()
        captionController.reset()
        sessionCoordinator.teardown()
        stopAutoQualityPolling()
        resetAutoQualitySamples()
        activeChannel = nil
        activeAiring = nil
        isPromoted = false
        lastAutoSkippedSegmentStart = nil
    }

    private func handleRemoteContentChange(_ content: SyncPlayContent) {
        Task { @MainActor [weak self] in
            guard let self else { return }
            if content.type == "recording", let recId = content.recordingId, !recId.isEmpty {
                if activeRecording?.recordingId != recId {
                    let dummyRec = HDHomeRunRecording(
                        recordingId: recId,
                        title: content.title ?? "Recording",
                        channelNumber: content.channelNumber,
                        playUrl: "/api/recordings/stream/\(recId)"
                    )
                    Task {
                        await playRecording(dummyRec)
                    }
                }
            } else if content.type == "channel", let chNum = content.channelNumber, !chNum.isEmpty {
                if activeChannel?.channelNumber != chNum {
                    let dummyCh = HDHomeRunChannel(
                        channelNumber: chNum,
                        name: content.title ?? chNum
                    )
                    Task {
                        await playChannel(channel: dummyCh)
                    }
                }
            }
        }
    }
}
