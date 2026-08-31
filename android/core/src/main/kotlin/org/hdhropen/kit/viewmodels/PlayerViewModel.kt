package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.*
import org.hdhropen.kit.utilities.Log

/** How the current session is being delivered - set by PlayerViewModel at
 * each stream-URL-construction call site, since PlayerEngine has no way to
 * infer this from the URL alone (both Direct and HLS URLs just look like
 * media URLs to it). */
enum class PlaybackMode {
    Direct,
    ServerTranscodedHls
}

@UnstableApi
class PlayerViewModel(
    private val apiClient: APIClient,
    val watchSessionManager: WatchSessionManager,
    val playerEngine: PlayerEngine = PlayerEngine(),
    val captionController: CaptionController = CaptionController(),
    private val playbackPreferences: PlaybackPreferences = PlaybackPreferences()
) : ViewModel() {
    private companion object {
        // Live captions are extracted incrementally by the backend; re-fetching
        // more often than this just re-downloads/re-parses an ever-larger VTT
        // for little freshness gain, since Android does a full-replace rather
        // than an incremental append. The dominant source of caption lag is
        // server-side CEA-608/708 roll-up decode latency (10-15s, see CC-3 in
        // TODO.md) - this only trims the client's own added delay, so it's
        // kept short rather than tuned much further down.
        const val CAPTION_POLL_INTERVAL_MS = 1_500L

        // Live extraction (segment decode + poll interval) routinely delivers a
        // cue 10-15s after the dialogue it transcribes - well past that cue's
        // own few-second [start, end] window relative to live playback. A cue
        // that arrives already-expired would never satisfy CaptionController's
        // "currentTime is inside this cue" check, so it would just silently
        // never show. Stretching such a cue's window to start from whenever it
        // actually arrived keeps it on screen for a bit instead.
        const val LIVE_CUE_STRETCH_SECONDS = 4.0
    }

    private var captionPollJob: Job? = null

    // Keyed by CaptionCue.id (stable across polls - derived from the raw,
    // pre-alignment start/end/text the backend won't change once emitted).
    // Android's setCues() is a full-replace each poll rather than web's
    // incremental append, so a stretch decision made for a cue on one poll
    // has to be remembered and reapplied on every later poll that re-sees the
    // same cue, or it would flicker between its natural (expired) window and
    // a freshly-recomputed stretch window each time.
    private val stretchedCueDisplay = mutableMapOf<String, Pair<Double, Double>>()
    private var nextStretchSlotAbsolute = 0.0

    // The raw (pre-alignment) cues from the most recent fetchCaptionsOnce -
    // kept so a seek/skip can re-run alignLiveCues immediately against the
    // player's new position without waiting for the next poll or issuing a
    // network fetch.
    private var lastRawCues: List<CaptionCue> = emptyList()

    private val _activeChannel = MutableStateFlow<HDHomeRunChannel?>(null)
    val activeChannel: StateFlow<HDHomeRunChannel?> = _activeChannel.asStateFlow()

    private val _activeAiring = MutableStateFlow<HDHomeRunGuideEntry?>(null)
    val activeAiring: StateFlow<HDHomeRunGuideEntry?> = _activeAiring.asStateFlow()

    private val _activeRecording = MutableStateFlow<HDHomeRunRecording?>(null)
    val activeRecording: StateFlow<HDHomeRunRecording?> = _activeRecording.asStateFlow()

    private val _isWatchSession = MutableStateFlow(false)
    val isWatchSession: StateFlow<Boolean> = _isWatchSession.asStateFlow()

    private val _activeHLSSessionId = MutableStateFlow<String?>(null)
    val activeHLSSessionId: StateFlow<String?> = _activeHLSSessionId.asStateFlow()

    private val _playbackMode = MutableStateFlow<PlaybackMode?>(null)
    val playbackMode: StateFlow<PlaybackMode?> = _playbackMode.asStateFlow()

    private val _thumbnailCues = MutableStateFlow<List<ThumbnailCue>>(emptyList())
    val thumbnailCues: StateFlow<List<ThumbnailCue>> = _thumbnailCues.asStateFlow()

    private val _thumbnailSpriteURL = MutableStateFlow<String?>(null)
    val thumbnailSpriteURL: StateFlow<String?> = _thumbnailSpriteURL.asStateFlow()

    private val _isPromoting = MutableStateFlow(false)
    val isPromoting: StateFlow<Boolean> = _isPromoting.asStateFlow()

    private val _isPromoted = MutableStateFlow(false)
    val isPromoted: StateFlow<Boolean> = _isPromoted.asStateFlow()

    private val _isSwitchingAudioTrack = MutableStateFlow(false)
    val isSwitchingAudioTrack: StateFlow<Boolean> = _isSwitchingAudioTrack.asStateFlow()

    val showAudioMenu = MutableStateFlow(false)
    val showSettingsOverlay = MutableStateFlow(false)

    init {
        // Sync player engine time with captions
        viewModelScope.launch {
            playerEngine.currentTime.collect { time ->
                captionController.updatePlaybackTime(time)
            }
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

    fun playChannel(channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry? = null) {
        viewModelScope.launch {
            closePlayer()
            _activeChannel.value = channel
            _activeAiring.value = airing ?: channel.now

            val baseURL = apiClient.baseURL

            // 0. Direct play: skips the watch session (so no live pause/rewind
            // and no tuner sharing with other viewers) and server-side
            // transcoding entirely, in exchange for lower latency/CPU - only
            // for clients whose own platform can decode the tuner's raw
            // MPEG-2/MPEG-TS stream, which ExoPlayer can.
            if (playbackPreferences.directPlayEnabled.value) {
                val directURL = StreamURLBuilder.liveStreamURL(baseURL, channel.channelNumber, direct = true)
                _isWatchSession.value = false
                _activeRecording.value = null
                _activeHLSSessionId.value = null
                _playbackMode.value = PlaybackMode.Direct
                playerEngine.loadMedia(url = directURL, isLive = true, isSeekable = false, headers = hlsAuthHeaders())
                return@launch
            }

            // 1. Try starting a watch session for live pause/rewind, packaged as HLS
            try {
                val watchRec = watchSessionManager.startWatch(channel.channelNumber)
                val playUrl = watchRec?.playUrl
                if (watchRec != null && playUrl != null) {
                    val hlsSession = apiClient.createRecordingHLSSession(
                        url = playUrl,
                        recordingId = watchRec.recordingId,
                        provider = watchRec.provider
                    )
                    val playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL = baseURL, sessionId = hlsSession.sessionId)
                    _activeRecording.value = watchRec
                    _isWatchSession.value = true
                    _activeHLSSessionId.value = hlsSession.sessionId
                    _playbackMode.value = PlaybackMode.ServerTranscodedHls
                    playerEngine.loadMedia(url = playlistURL, isLive = true, isSeekable = true, headers = hlsAuthHeaders())
                    loadRecordingMetadata(watchRec)
                    return@launch
                }
            } catch (e: Exception) {
                Log.player.warning("Watch session auto-start failed, falling back to direct HLS: ${e.localizedMessage}")
            }

            // 2. Direct HLS streaming fallback
            try {
                val hlsSession = apiClient.createChannelHLSSession(channel.channelNumber)
                val playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL = baseURL, sessionId = hlsSession.sessionId)
                _isWatchSession.value = false
                _activeRecording.value = null
                _activeHLSSessionId.value = hlsSession.sessionId
                _playbackMode.value = PlaybackMode.ServerTranscodedHls
                playerEngine.loadMedia(url = playlistURL, isLive = true, isSeekable = false, headers = hlsAuthHeaders())
            } catch (e: Exception) {
                Log.player.error("Direct HLS channel stream failed: ${e.localizedMessage}")
                playerEngine.setFailed(e.localizedMessage ?: "Failed to start stream")
            }
        }
    }

    fun playRecording(recording: HDHomeRunRecording) {
        viewModelScope.launch {
            closePlayer()
            _activeRecording.value = recording
            _activeChannel.value = null
            _activeAiring.value = null
            _isWatchSession.value = false

            val baseURL = apiClient.baseURL
            val playUrl = recording.playUrl ?: return@launch

            try {
                val hlsSession = apiClient.createRecordingHLSSession(
                    url = playUrl,
                    recordingId = recording.recordingId,
                    provider = recording.provider
                )
                val playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL = baseURL, sessionId = hlsSession.sessionId)
                _activeHLSSessionId.value = hlsSession.sessionId
                _playbackMode.value = PlaybackMode.ServerTranscodedHls
                playerEngine.loadMedia(url = playlistURL, isLive = recording.isInProgress, isSeekable = true, headers = hlsAuthHeaders())
                loadRecordingMetadata(recording)
            } catch (e: Exception) {
                Log.player.error("Recording HLS stream failed: ${e.localizedMessage}")
                playerEngine.setFailed(e.localizedMessage ?: "Failed to play recording")
            }
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
            } finally {
                _isPromoting.value = false
            }
        }
    }

    fun selectAudioTrack(track: HDHomeRunRecordingAudioInfo) {
        // Audio track selection is baked into the HLS packaging itself
        // (backend maps a specific source audio stream via ffmpeg's `-map`
        // when building the session) rather than exposed as switchable
        // in-stream tracks on the produced playlist, so "switching"
        // requires starting a new HLS session with the new audio index
        // and resuming playback at the current position.
        if (_isSwitchingAudioTrack.value || track.index == playerEngine.currentAudioTrack.value?.index) return
        val recording = _activeRecording.value ?: return
        val playUrl = recording.playUrl
        if (playUrl.isNullOrEmpty()) return

        viewModelScope.launch {
            _isSwitchingAudioTrack.value = true
            try {
                val resumeTime = playerEngine.currentTime.value
                val isLive = playerEngine.isLive.value
                val isSeekable = playerEngine.isSeekable.value
                val previousSessionId = _activeHLSSessionId.value
                val previousAudioTracks = playerEngine.availableAudioTracks.value
                val previousVideoSpecs = playerEngine.videoSpecs.value
                val previousTranscodeInfo = playerEngine.transcodeInfo.value
                val baseURL = apiClient.baseURL

                val hlsSession = apiClient.createRecordingHLSSession(
                    url = playUrl,
                    recordingId = recording.recordingId,
                    start = resumeTime,
                    audioIndex = track.index,
                    provider = recording.provider
                )
                val playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL = baseURL, sessionId = hlsSession.sessionId)
                _activeHLSSessionId.value = hlsSession.sessionId
                // loadMedia() calls reset() internally, which wipes the audio
                // track list/video specs - restore them since they describe the
                // underlying recording and don't change when only the mapped
                // audio stream does.
                playerEngine.loadMedia(url = playlistURL, isLive = isLive, isSeekable = isSeekable, headers = hlsAuthHeaders())
                playerEngine.setAudioTracks(previousAudioTracks)
                playerEngine.setVideoSpecs(previousVideoSpecs)
                playerEngine.setTranscodeInfo(previousTranscodeInfo)
                playerEngine.selectAudioTrack(track)

                if (previousSessionId != null) {
                    viewModelScope.launch {
                        try {
                            apiClient.stopHLSSession(previousSessionId)
                        } catch (e: Exception) {
                            // Ignore
                        }
                    }
                }
            } catch (e: Exception) {
                Log.player.error("Audio track switch failed: ${e.localizedMessage}")
            } finally {
                _isSwitchingAudioTrack.value = false
            }
        }
    }

    private fun hlsAuthHeaders(): Map<String, String> =
        apiClient.bearerToken?.let { mapOf("Authorization" to "Bearer $it") } ?: emptyMap()

    private fun loadRecordingMetadata(recording: HDHomeRunRecording) {
        val recId = recording.recordingId ?: return
        val playUrl = recording.playUrl ?: return

        viewModelScope.launch {
            val baseURL = apiClient.baseURL

            // Fetch Detail (audio tracks, video specs)
            try {
                val detail = apiClient.getRecordingDetail(
                    url = playUrl,
                    recordingId = recId,
                    start = recording.start,
                    recordEnd = recording.recordEnd,
                    provider = recording.provider
                )
                playerEngine.setAudioTracks(detail.audio)
                playerEngine.setVideoSpecs(detail.video)
                playerEngine.setTranscodeInfo(detail.transcode)
                detail.durationSeconds?.let { dur ->
                    if (dur > 0) playerEngine.setDuration(dur)
                }
            } catch (e: Exception) {
                // Detail is optional
            }

            // Fetch Thumbnails VTT
            try {
                val vttURL = StreamURLBuilder.thumbnailVttURL(
                    baseURL = baseURL,
                    recordingId = recId,
                    playUrl = playUrl,
                    recordEnd = recording.recordEnd,
                    provider = recording.provider
                )
                _thumbnailSpriteURL.value = StreamURLBuilder.thumbnailSpriteURL(
                    baseURL = baseURL,
                    recordingId = recId,
                    playUrl = playUrl,
                    recordEnd = recording.recordEnd,
                    provider = recording.provider
                )
                val vttString = apiClient.fetchRawString(vttURL)
                _thumbnailCues.value = VTTParser.parseThumbnailVtt(vttString)
            } catch (e: Exception) {
                // Thumbnails are optional
            }

            fetchCaptionsOnce(recording)
            startCaptionPolling(recording)
        }
    }

    private suspend fun fetchCaptionsOnce(recording: HDHomeRunRecording) {
        val recId = recording.recordingId ?: return
        val playUrl = recording.playUrl ?: return
        try {
            val capURL = StreamURLBuilder.captionsURL(
                baseURL = apiClient.baseURL,
                recordingId = recId,
                playUrl = playUrl,
                recordEnd = recording.recordEnd,
                provider = recording.provider
            )
            val capString = apiClient.fetchRawString(capURL)
            val cues = VTTParser.parseCaptions(capString)
            lastRawCues = cues
            captionController.setCues(alignLiveCues(recording, cues))
        } catch (e: Exception) {
            // Captions are optional / not extracted yet - poller (if running) retries next tick
        }
    }

    /** Seek/skip wrappers that delegate to playerEngine and then immediately
     * re-run live-cue alignment against the new position, instead of leaving
     * captions stale until the next poll tick (up to CAPTION_POLL_INTERVAL_MS
     * away). This covers scrubbing, FF/rewind on an in-progress recording,
     * and rewinding live TV (which is just an in-progress watch-session
     * recording under the hood). Callers should use these instead of calling
     * playerEngine's seek/skipForward/skipBackward directly. */
    fun seek(seconds: Double) {
        playerEngine.seek(seconds)
        resyncCaptionsAfterSeek()
    }

    fun skipForward(seconds: Double = 10.0) {
        playerEngine.skipForward(seconds)
        resyncCaptionsAfterSeek()
    }

    fun skipBackward(seconds: Double = 10.0) {
        playerEngine.skipBackward(seconds)
        resyncCaptionsAfterSeek()
    }

    /** Deliberately does NOT call resetCueStretch(): stretchedCueDisplay's
     * windows are already absolute-time and cue-id-keyed, so alignLiveCues
     * converts them to display coordinates fresh on every call via the
     * current baseOffsetSeconds - no reason to touch it here. Clearing it
     * would make nearly every already-stretched cue in lastRawCues (Android
     * fetches the full history each time, not an incremental append) look
     * "newly arrived" simultaneously, replaying the whole caption history in
     * back-to-back stretch slots right after a seek. */
    private fun resyncCaptionsAfterSeek() {
        val recording = _activeRecording.value ?: return
        if (!recording.isInProgress) return
        captionController.setCues(alignLiveCues(recording, lastRawCues))
    }

    /** While a recording is in progress, the backend serves cue timestamps
     * anchored to the capture's absolute start (`recording.start`), but the
     * HLS session actually being played is a fresh rolling live window whose
     * own position clock has no fixed relationship to that origin - so raw
     * cue times drift against `playerEngine.currentTime` and cues appear to
     * repeat/misalign. Shift cues by the gap between elapsed capture time
     * (computable locally, since `recording.start` is an absolute epoch) and
     * the player's own position; recomputed on every poll so it tracks a
     * live-growing HLS window instead of freezing at its first estimate.
     *
     * That shift alone isn't enough while live, though: extraction lag means
     * a cue's natural (shifted) window has often already passed the current
     * player position by the time it arrives. Such cues get "stretched" to a
     * short display window starting from whenever they actually showed up
     * instead, mirroring the web client's live-cue handling
     * (`frontend/src/lib/caption-controller.ts`). Cues that are due to arrive
     * (or already displaying) reach their real window as normal. */
    private fun alignLiveCues(recording: HDHomeRunRecording, cues: List<CaptionCue>): List<CaptionCue> {
        val start = recording.start
        if (!recording.isInProgress || start == null) return cues
        val elapsedCaptureSeconds = (System.currentTimeMillis() / 1000.0) - start
        val playerTime = playerEngine.currentTime.value
        val baseOffsetSeconds = elapsedCaptureSeconds - playerTime

        return cues.mapNotNull { cue ->
            val (absStart, absEnd) = stretchedCueDisplay[cue.id] ?: run {
                val naturalEnd = cue.end - baseOffsetSeconds
                if (naturalEnd > playerTime) {
                    cue.start to cue.end
                } else {
                    val slotStart = maxOf(cue.start, nextStretchSlotAbsolute, elapsedCaptureSeconds)
                    val slotEnd = slotStart + LIVE_CUE_STRETCH_SECONDS
                    stretchedCueDisplay[cue.id] = slotStart to slotEnd
                    nextStretchSlotAbsolute = slotEnd
                    slotStart to slotEnd
                }
            }
            val displayEnd = absEnd - baseOffsetSeconds
            if (displayEnd <= 0) return@mapNotNull null
            cue.copy(start = (absStart - baseOffsetSeconds).coerceAtLeast(0.0), end = displayEnd)
        }
    }

    /** Clears live-cue stretch bookkeeping so a new playback session doesn't
     * reuse stale slot/display decisions from a previous one. */
    private fun resetCueStretch() {
        stretchedCueDisplay.clear()
        nextStretchSlotAbsolute = 0.0
        lastRawCues = emptyList()
    }

    /** Periodically re-fetches captions while a recording is in progress,
     * since the backend extracts live captions incrementally and expects
     * clients to poll rather than fetch once. Stops after the first fetch
     * made once the recording is no longer in progress (its final, complete
     * VTT). Covers both live watch sessions (`playChannel`) and DVR items
     * still recording when opened from the recordings list (`playRecording`)
     * - both call this via `loadRecordingMetadata`. */
    private fun startCaptionPolling(recording: HDHomeRunRecording) {
        if (!recording.isInProgress) return
        captionPollJob?.cancel()
        captionPollJob = viewModelScope.launch {
            while (isActive) {
                delay(CAPTION_POLL_INTERVAL_MS)
                val current = _activeRecording.value ?: break
                val wasInProgress = current.isInProgress
                fetchCaptionsOnce(current)
                if (!wasInProgress) break
            }
        }
    }

    private fun stopCaptionPolling() {
        captionPollJob?.cancel()
        captionPollJob = null
    }

    fun closePlayer() {
        playerEngine.reset()
        watchSessionManager.stopWatch()
        stopCaptionPolling()
        captionController.reset()
        resetCueStretch()

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
    }
}
