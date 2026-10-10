package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.SyncPlayClient
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.*
import org.hdhropen.kit.utilities.Log
import kotlin.math.abs

/** How the current session is being delivered - set by PlayerViewModel at
 * each stream-URL-construction call site, since PlayerEngine has no way to
 * infer this from the URL alone (both Direct and HLS URLs just look like
 * media URLs to it). */
enum class PlaybackMode {
    Direct,
    ServerTranscodedHls
}

// AutoTier and its ladder helpers live in PlayerViewModel+AutoQuality.kt,
// alongside the auto-quality methods that are their only callers.

@UnstableApi
class PlayerViewModel(
    // Not private: used from PlayerViewModel+Streaming.kt's HLS session
    // negotiation.
    internal val apiClient: APIClient,
    val watchSessionManager: WatchSessionManager,
    val playerEngine: PlayerEngine = PlayerEngine(),
    val captionController: CaptionController = CaptionController(),
    // Not private: read from PlayerViewModel+Streaming.kt's playChannel()
    // and PlayerViewModel+AutoQuality.kt's initializeQualityForNewSession().
    internal val playbackPreferences: PlaybackPreferences = PlaybackPreferences(),
    val liveCaptionAligner: LiveCaptionAligner = LiveCaptionAligner()
) : ViewModel() {
    private companion object {
        // Shared with HDHomeRunPlayer.svelte's auto-quality design - keep
        // these in sync across clients.
        const val STALL_WINDOW_MS = 20_000L
        const val STALL_THRESHOLD = 2
    }

    // Not private: cancelled/started from PlayerViewModel+Streaming.kt's
    // startCaptionPolling()/stopCaptionPolling().
    internal var captionPollJob: Job? = null

    // Not private: read/written from PlayerViewModel+Streaming.kt's HLS
    // session negotiation.
    internal val _activeChannel = MutableStateFlow<HDHomeRunChannel?>(null)
    val activeChannel: StateFlow<HDHomeRunChannel?> = _activeChannel.asStateFlow()

    internal val _activeAiring = MutableStateFlow<HDHomeRunGuideEntry?>(null)
    val activeAiring: StateFlow<HDHomeRunGuideEntry?> = _activeAiring.asStateFlow()

    internal val _activeRecording = MutableStateFlow<HDHomeRunRecording?>(null)
    val activeRecording: StateFlow<HDHomeRunRecording?> = _activeRecording.asStateFlow()

    internal val _isWatchSession = MutableStateFlow(false)
    val isWatchSession: StateFlow<Boolean> = _isWatchSession.asStateFlow()

    internal val _activeHLSSessionId = MutableStateFlow<String?>(null)
    val activeHLSSessionId: StateFlow<String?> = _activeHLSSessionId.asStateFlow()

    // Not private: cancelled/started from PlayerViewModel+Streaming.kt's
    // startHLSHeartbeat()/stopHLSHeartbeat().
    internal var hlsHeartbeatJob: Job? = null

    // Not private: cancelled/started from PlayerViewModel+Streaming.kt's
    // seekRecordingViaServer(), cancelled from closePlayer() here.
    internal var serverSeekJob: Job? = null

    // startHLSHeartbeat()/stopHLSHeartbeat() live in
    // PlayerViewModel+Streaming.kt, alongside the HLS session negotiation
    // methods that are their only callers.

    // Not private: read from PlayerViewModel+AutoQuality.kt's
    // startAutoQualityPolling().
    internal val _playbackMode = MutableStateFlow<PlaybackMode?>(null)
    val playbackMode: StateFlow<PlaybackMode?> = _playbackMode.asStateFlow()

    // Not private: written from PlayerViewModel+Streaming.kt's
    // loadRecordingMetadata().
    internal val _thumbnailCues = MutableStateFlow<List<ThumbnailCue>>(emptyList())
    val thumbnailCues: StateFlow<List<ThumbnailCue>> = _thumbnailCues.asStateFlow()

    internal val _thumbnailSpriteURL = MutableStateFlow<String?>(null)
    val thumbnailSpriteURL: StateFlow<String?> = _thumbnailSpriteURL.asStateFlow()

    private val _isPromoting = MutableStateFlow(false)
    val isPromoting: StateFlow<Boolean> = _isPromoting.asStateFlow()

    private val _isPromoted = MutableStateFlow(false)
    val isPromoted: StateFlow<Boolean> = _isPromoted.asStateFlow()

    // Not private: written from PlayerViewModel+Streaming.kt's
    // selectAudioTrack().
    internal val _isSwitchingAudioTrack = MutableStateFlow(false)
    val isSwitchingAudioTrack: StateFlow<Boolean> = _isSwitchingAudioTrack.asStateFlow()

    // Per-session quality pick, refreshed from the persisted default
    // (playbackPreferences.qualityPreference, set from SettingsScreen) each
    // time a new channel/recording starts - selectQuality() below only
    // changes it for the current session, mirroring how currentAudioTrack
    // is per-session with no persistence of its own.
    // Not private: read from PlayerViewModel+AutoQuality.kt's
    // maybeStartAutoQualityPolling()/startAutoQualityPolling().
    internal val _quality = MutableStateFlow(playbackPreferences.qualityPreference.value)
    val quality: StateFlow<QualityPreference> = _quality.asStateFlow()

    // Not private: written from PlayerViewModel+Streaming.kt's
    // switchToQuality().
    internal val _isSwitchingQuality = MutableStateFlow(false)
    val isSwitchingQuality: StateFlow<Boolean> = _isSwitchingQuality.asStateFlow()

    // The concrete tier AUTO is currently resolved to - tracked separately
    // from _quality (which stays AUTO while this moves between tiers).
    // Not private: read/written from PlayerViewModel+AutoQuality.kt's
    // auto-quality methods, split into that file to keep this class under
    // detekt's LargeClass cap.
    internal var autoEffectiveTier: AutoTier = AutoTier.HIGH

    internal var autoQualityPollJob: Job? = null
    internal val stallTimestamps = mutableListOf<Long>()
    internal val speedSamplesMbps = mutableListOf<Double>()
    internal val bufferedAheadSamples = mutableListOf<Double>()

    // Not private: written from PlayerViewModel+Streaming.kt's
    // selectAudioTrack()/switchToQuality().
    internal val _transientError = MutableStateFlow<String?>(null)
    val transientError: StateFlow<String?> = _transientError.asStateFlow()

    fun clearTransientError() {
        _transientError.value = null
    }

    // Not private: written from PlayerViewModel+Streaming.kt's playChannel().
    internal val _fallbackNotice = MutableStateFlow<String?>(null)
    val fallbackNotice: StateFlow<String?> = _fallbackNotice.asStateFlow()

    private val _activeCommercialSegment = MutableStateFlow<CommercialSegment?>(null)
    val activeCommercialSegment: StateFlow<CommercialSegment?> = _activeCommercialSegment.asStateFlow()

    // Guards auto-skip to at most once per segment. Compared against the
    // active segment's startSeconds rather than reset on a timer, so it
    // survives seekRecordingViaServer()'s segment-list restore (which must
    // not re-trigger a skip already performed) and is only cleared by
    // closePlayer() when a genuinely new recording/channel loads.
    private var lastAutoSkippedSegmentStart: Double? = null

    private val _autoSkipCommercialPulse = MutableStateFlow(0L)
    val autoSkipCommercialPulse: StateFlow<Long> = _autoSkipCommercialPulse.asStateFlow()

    val autoSkipCommercialsEnabled: StateFlow<Boolean> = playbackPreferences.autoSkipCommercialsEnabled

    fun clearFallbackNotice() {
        _fallbackNotice.value = null
    }

    val syncPlayClient: SyncPlayClient = runCatching {
        SyncPlayClient(
            httpClient = apiClient.httpClient,
            json = apiClient.json,
            coroutineScope = viewModelScope
        )
    }.getOrElse {
        SyncPlayClient(
            httpClient = okhttp3.OkHttpClient(),
            json = kotlinx.serialization.json.Json { ignoreUnknownKeys = true; isLenient = true; encodeDefaults = true; coerceInputValues = true },
            coroutineScope = viewModelScope
        )
    }

    val syncPlayRoom: StateFlow<SyncPlayRoom?> = syncPlayClient.room
    val syncPlayParticipants: StateFlow<List<SyncPlayParticipant>> = syncPlayClient.participants
    val isSyncPlayHost: StateFlow<Boolean> = syncPlayClient.isHost
    val syncPlayConnected: StateFlow<Boolean> = syncPlayClient.isConnected
    val syncPlayPingMs: StateFlow<Double> = syncPlayClient.pingMs

    init {
        // Sync player engine time with captions
        viewModelScope.launch {
            playerEngine.currentTime.collect { time ->
                captionController.updatePlaybackTime(time)
            }
        }

        // Derive the commercial segment (if any) containing the current playback
        // position, driving the "Skip Commercial" affordance on every surface.
        viewModelScope.launch {
            combine(playerEngine.currentTime, playerEngine.commercialSegments) { time, segments ->
                segments.firstOrNull { time >= it.startSeconds && time < it.endSeconds }
            }.collect { segment ->
                _activeCommercialSegment.value = segment
            }
        }

        // Auto-skip commercials, when enabled, firing at most once per
        // segment via lastAutoSkippedSegmentStart.
        viewModelScope.launch {
            _activeCommercialSegment.collect { segment ->
                if (segment != null &&
                    playbackPreferences.autoSkipCommercialsEnabled.value &&
                    lastAutoSkippedSegmentStart != segment.startSeconds
                ) {
                    lastAutoSkippedSegmentStart = segment.startSeconds
                    skipActiveCommercial()
                    _autoSkipCommercialPulse.value = System.currentTimeMillis()
                }
            }
        }

        // Reactive stall path - unlike the 5s poll loop, this reacts the
        // instant ExoPlayer reports a stall, same policy as
        // recordStallAndMaybeDowngrade() in HDHomeRunPlayer.svelte.
        viewModelScope.launch {
            playerEngine.stallPulse.collect { pulse ->
                if (pulse == 0L || _quality.value != QualityPreference.AUTO) return@collect
                stallTimestamps.add(pulse)
                stallTimestamps.removeAll { pulse - it > STALL_WINDOW_MS }
                if (stallTimestamps.size >= STALL_THRESHOLD) {
                    stallTimestamps.clear()
                    applyAutoDowngradeOneTier()
                }
            }
        }

        // Wire SyncPlayClient callbacks
        syncPlayClient.getCurrentPosition = { playerEngine.currentTime.value }
        syncPlayClient.isPlayerReady = {
            playerEngine.state.value == PlaybackState.Playing || playerEngine.state.value == PlaybackState.Paused
        }
        syncPlayClient.onRemotePlay = { position, rate ->
            val diff = abs(playerEngine.currentTime.value - position)
            if (diff > 2.0) {
                playerEngine.seek(position)
            }
            playerEngine.play()
        }
        syncPlayClient.onRemotePause = { position ->
            playerEngine.pause()
            val diff = abs(playerEngine.currentTime.value - position)
            if (diff > 0.5) {
                playerEngine.seek(position)
            }
        }
        syncPlayClient.onRemoteSeek = { position ->
            playerEngine.seek(position)
        }
        syncPlayClient.onRemoteContentChange = { content ->
            handleRemoteContentChange(content)
        }
    }

    val isPlaying: Boolean
        get() = playerEngine.state.value == PlaybackState.Playing

    val mediaTitle: String
        get() {
            _activeRecording.value?.let { return it.title }
            _activeChannel.value?.let { ch ->
                _activeAiring.value?.let { airing ->
                    return "${ch.channelNumber} ${airing.title}"
                }
                return "${ch.channelNumber} ${ch.name}"
            }
            return "Live TV"
        }

    val mediaSubtitle: String?
        get() {
            _activeRecording.value?.let { rec ->
                if (rec.episodeTitle != null && rec.episodeDesignation != null) {
                    return "${rec.episodeDesignation} • ${rec.episodeTitle}"
                }
                return rec.episodeTitle ?: rec.episodeDesignation ?: rec.channelName
            }
            _activeAiring.value?.let { airing ->
                if (airing.episodeTitle != null && airing.episodeNumber != null) {
                    return "${airing.episodeNumber} • ${airing.episodeTitle}"
                }
                return airing.episodeTitle ?: airing.synopsis
            }
            return _activeChannel.value?.name
        }

    // playChannel()/playRecording()/setPlaybackError() live in
    // PlayerViewModel+Streaming.kt, alongside the rest of the HLS session
    // negotiation.

    fun retry() {
        val channel = _activeChannel.value
        val airing = _activeAiring.value
        val recording = _activeRecording.value
        when {
            channel != null -> playChannel(channel, airing)
            recording != null -> playRecording(recording)
        }
    }

    fun promoteToRecording() {
        viewModelScope.launch {
            if (!_isWatchSession.value || _isPromoting.value) return@launch
            _isPromoting.value = true
            try {
                val promoted = watchSessionManager.promoteWatch()
                _activeRecording.value = promoted
                _isPromoted.value = true
                Log.player.info("Promoted live watch to DVR recording: ${promoted.title}")
            } catch (e: Exception) {
                Log.player.error("Failed to promote watch session: ${e.localizedMessage}")
                _transientError.value = "Failed to save recording: ${e.localizedMessage ?: "Unknown error"}"
            } finally {
                _isPromoting.value = false
            }
        }
    }

    // selectAudioTrack() lives in PlayerViewModel+Streaming.kt.
    // initializeQualityForNewSession() lives in PlayerViewModel+AutoQuality.kt.

    /** User-facing quality picker entry point - parity with selectAudioTrack(). */
    fun selectQuality(preference: QualityPreference) {
        if (_playbackMode.value == PlaybackMode.Direct || preference == _quality.value) return
        _quality.value = preference
        if (preference == QualityPreference.AUTO) {
            autoEffectiveTier = AutoTier.HIGH
            switchToQuality(AutoTier.HIGH.backendValue)
            startAutoQualityPolling()
        } else {
            stopAutoQualityPolling()
            autoEffectiveTier = preference.toAutoTier()
            switchToQuality(preference.backendValue)
        }
    }

    // switchToQuality()/hlsAuthHeaders()/loadRecordingMetadata()/
    // fetchCaptionsOnce() live in PlayerViewModel+Streaming.kt.

    fun play() {
        playerEngine.play()
        if (syncPlayClient.isConnected.value) {
            syncPlayClient.sendPlay(playerEngine.currentTime.value)
        }
    }

    fun pause() {
        playerEngine.pause()
        if (syncPlayClient.isConnected.value) {
            syncPlayClient.sendPause(playerEngine.currentTime.value)
        }
    }

    fun togglePlayPause() {
        if (playerEngine.state.value == PlaybackState.Playing) {
            pause()
        } else {
            play()
        }
    }

    /** Seek/skip wrappers that delegate to playerEngine, broadcast via SyncPlay
     * if connected, and immediately re-run live-cue alignment against the new position. */
    fun seek(seconds: Double) {
        val dur = if (playerEngine.duration.value > 0) playerEngine.duration.value else seconds
        val clamped = seconds.coerceIn(0.0, dur)
        val recording = _activeRecording.value
        val playUrl = recording?.playUrl
        if (recording != null && !playUrl.isNullOrEmpty() && !playerEngine.isPositionInSeekableRange(clamped)) {
            seekRecordingViaServer(recording, playUrl, clamped)
        } else {
            playerEngine.seek(clamped)
        }
        resyncCaptionsAfterSeek()
        if (syncPlayClient.isConnected.value) {
            syncPlayClient.sendSeek(clamped)
        }
    }

    // seekRecordingViaServer() lives in PlayerViewModel+Streaming.kt.

    fun skipForward(seconds: Double = 10.0) {
        val target = playerEngine.currentTime.value + seconds
        seek(target)
    }

    fun skipBackward(seconds: Double = 10.0) {
        val target = (playerEngine.currentTime.value - seconds).coerceAtLeast(0.0)
        seek(target)
    }

    fun skipActiveCommercial() {
        val segment = _activeCommercialSegment.value ?: return
        seek(segment.endSeconds)
    }

    fun createSyncPlayRoom(userName: String, onComplete: ((Result<SyncPlayRoom>) -> Unit)? = null) {
        viewModelScope.launch {
            try {
                val content = currentSyncPlayContent() ?: SyncPlayContent(type = "channel", id = "")
                val resp = apiClient.createSyncPlayRoom(content = content, userName = userName)
                val wsUrl = apiClient.syncPlayWsUrl(resp.room.roomCode, userName)
                syncPlayClient.connect(wsUrl, apiClient.bearerToken)
                onComplete?.invoke(Result.success(resp.room))
            } catch (e: Exception) {
                Log.network.error("Failed to create SyncPlay room: ${e.localizedMessage}")
                onComplete?.invoke(Result.failure(e))
            }
        }
    }

    fun joinSyncPlayRoom(roomCode: String, userName: String, onComplete: ((Result<Unit>) -> Unit)? = null) {
        viewModelScope.launch {
            try {
                val wsUrl = apiClient.syncPlayWsUrl(roomCode, userName)
                syncPlayClient.connect(wsUrl, apiClient.bearerToken)
                onComplete?.invoke(Result.success(Unit))
            } catch (e: Exception) {
                Log.network.error("Failed to join SyncPlay room: ${e.localizedMessage}")
                onComplete?.invoke(Result.failure(e))
            }
        }
    }

    fun leaveSyncPlayRoom() {
        syncPlayClient.disconnect()
    }

    fun transferSyncPlayHost(targetSessionId: String) {
        syncPlayClient.transferHost(targetSessionId)
    }

    private fun currentSyncPlayContent(): SyncPlayContent? {
        _activeRecording.value?.let { rec ->
            return SyncPlayContent(
                type = "recording",
                id = rec.recordingId ?: "",
                title = rec.title,
                channelNumber = rec.channelNumber,
                playUrl = rec.playUrl
            )
        }
        _activeChannel.value?.let { ch ->
            return SyncPlayContent(
                type = "channel",
                id = ch.channelNumber,
                channelNumber = ch.channelNumber,
                title = _activeAiring.value?.title ?: ch.name
            )
        }
        return null
    }

    private fun handleRemoteContentChange(content: SyncPlayContent) {
        if (content.type == "recording" && content.id.isNotEmpty()) {
            if (_activeRecording.value?.recordingId != content.id) {
                val dummyRec = HDHomeRunRecording(
                    recordingId = content.id,
                    title = content.title.ifEmpty { "Recording" },
                    channelNumber = content.channelNumber,
                    playUrl = content.playUrl ?: "/api/recordings/stream/${content.id}"
                )
                playRecording(dummyRec)
            }
        } else if (content.type == "channel" && (content.channelNumber != null || content.id.isNotEmpty())) {
            val chNum = content.channelNumber ?: content.id
            if (_activeChannel.value?.channelNumber != chNum) {
                val dummyCh = HDHomeRunChannel(
                    channelNumber = chNum,
                    name = content.title.ifEmpty { chNum }
                )
                playChannel(dummyCh)
            }
        }
    }

    // resyncCaptionsAfterSeek()/startCaptionPolling()/stopCaptionPolling()
    // live in PlayerViewModel+Streaming.kt.

    fun closePlayer() {
        serverSeekJob?.cancel()
        serverSeekJob = null
        stopHLSHeartbeat()
        stopAutoQualityPolling()
        resetAutoQualitySamples()
        playerEngine.reset()
        watchSessionManager.stopWatch()
        stopCaptionPolling()
        captionController.reset()
        liveCaptionAligner.reset()

        _activeHLSSessionId.value?.let { sessionId ->
            viewModelScope.launch {
                try {
                    apiClient.stopHLSSession(sessionId)
                } catch (e: Exception) {
                    // Ignore
                }
            }
        }

        _activeChannel.value = null
        _activeAiring.value = null
        _activeRecording.value = null
        _isWatchSession.value = false
        _activeHLSSessionId.value = null
        _playbackMode.value = null
        _isPromoted.value = false
        _thumbnailCues.value = emptyList()
        _thumbnailSpriteURL.value = null
        _fallbackNotice.value = null
        _transientError.value = null
        lastAutoSkippedSegmentStart = null
    }
}
