package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.APIError
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

@UnstableApi
class PlayerViewModel(
    private val apiClient: APIClient,
    val watchSessionManager: WatchSessionManager,
    val playerEngine: PlayerEngine = PlayerEngine(),
    val captionController: CaptionController = CaptionController(),
    private val playbackPreferences: PlaybackPreferences = PlaybackPreferences(),
    val liveCaptionAligner: LiveCaptionAligner = LiveCaptionAligner()
) : ViewModel() {
    private companion object {
        const val CAPTION_POLL_INTERVAL_MS = 1_500L
    }

    private var captionPollJob: Job? = null

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

    private var hlsHeartbeatJob: Job? = null
    private var serverSeekJob: Job? = null

    private fun startHLSHeartbeat(sessionId: String) {
        hlsHeartbeatJob?.cancel()
        hlsHeartbeatJob = viewModelScope.launch(Dispatchers.IO) {
            while (isActive) {
                delay(15_000)
                if (!isActive) break
                try {
                    apiClient.heartbeatHLSSession(sessionId)
                    Log.player.debug("Heartbeat sent for HLS session $sessionId")
                } catch (e: Exception) {
                    Log.player.warning("HLS heartbeat failed for $sessionId: ${e.localizedMessage}")
                }
            }
        }
    }

    private fun stopHLSHeartbeat() {
        hlsHeartbeatJob?.cancel()
        hlsHeartbeatJob = null
    }

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

    private val _transientError = MutableStateFlow<String?>(null)
    val transientError: StateFlow<String?> = _transientError.asStateFlow()

    fun clearTransientError() {
        _transientError.value = null
    }

    private val _fallbackNotice = MutableStateFlow<String?>(null)
    val fallbackNotice: StateFlow<String?> = _fallbackNotice.asStateFlow()

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

    fun playChannel(channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry? = null) {
        viewModelScope.launch {
            closePlayer()
            _activeChannel.value = channel
            _activeAiring.value = airing ?: channel.now

            if (syncPlayClient.isConnected.value && syncPlayClient.isHost.value) {
                syncPlayClient.changeContent(
                    SyncPlayContent(
                        type = "channel",
                        id = channel.channelNumber,
                        title = airing?.title ?: channel.name,
                        channelNumber = channel.channelNumber,
                        playUrl = channel.playbackUrl
                    )
                )
            }

            val baseURL = apiClient.baseURL

            // 0. Direct play: skips the watch session (so no live pause/rewind
            // and no tuner sharing with other viewers) and server-side
            // transcoding entirely, in exchange for lower latency/CPU - only
            // for clients whose own platform can decode the tuner's raw
            // MPEG-2/MPEG-TS stream, which ExoPlayer can.
            val artworkUrl = airing?.imageUrl ?: channel.now?.imageUrl

            if (playbackPreferences.directPlayEnabled.value) {
                val directURL = StreamURLBuilder.liveStreamURL(baseURL, channel.channelNumber, direct = true)
                _isWatchSession.value = false
                _activeRecording.value = null
                _activeHLSSessionId.value = null
                _playbackMode.value = PlaybackMode.Direct
                playerEngine.loadMedia(
                    url = directURL,
                    isLive = true,
                    isSeekable = false,
                    headers = hlsAuthHeaders(),
                    title = mediaTitle,
                    artworkUrl = artworkUrl
                )
                return@launch
            }

            val forCast = playerEngine.isCasting.value

            // 1. Try starting a watch session for live pause/rewind, packaged as HLS
            var watchStartFailed = false
            try {
                val watchRec = watchSessionManager.startWatch(channel.channelNumber)
                val playUrl = watchRec?.playUrl
                if (watchRec != null && playUrl != null) {
                    val hlsSession = apiClient.createRecordingHLSSession(
                        url = playUrl,
                        recordingId = watchRec.recordingId,
                        provider = watchRec.provider,
                        forCast = forCast
                    )
                    // Uses the server's own playlist_url rather than
                    // reconstructing it - when forCast is set, that URL is
                    // scoped under a cast token and can't be derived from
                    // sessionId alone.
                    val playlistURL = StreamURLBuilder.resolve(baseURL, hlsSession.playlistUrl)
                    _activeRecording.value = watchRec
                    _isWatchSession.value = true
                    _activeHLSSessionId.value = hlsSession.sessionId
                    startHLSHeartbeat(hlsSession.sessionId)
                    _playbackMode.value = PlaybackMode.ServerTranscodedHls
                    playerEngine.loadMedia(
                        url = playlistURL,
                        isLive = true,
                        isSeekable = true,
                        headers = hlsAuthHeaders(),
                        title = mediaTitle,
                        artworkUrl = artworkUrl ?: watchRec.imageUrl
                    )
                    loadRecordingMetadata(watchRec)
                    return@launch
                } else {
                    watchStartFailed = true
                }
            } catch (e: Exception) {
                Log.player.warning("Watch session auto-start failed, falling back to direct HLS: ${e.localizedMessage}")
                watchStartFailed = true
            }

            if (watchStartFailed) {
                _fallbackNotice.value = "Live pause unavailable for this stream"
            }

            // 2. Direct HLS streaming fallback
            try {
                val rec = apiClient.createChannelHLSSession(channel.channelNumber, forCast = forCast)
                val sessionId = rec.sessionId ?: throw APIError.DecodingError("Missing session_id")
                val playlistURL = rec.playlistUrl?.let { StreamURLBuilder.resolve(baseURL, it) }
                    ?: StreamURLBuilder.hlsPlaylistURL(baseURL = baseURL, sessionId = sessionId)
                _isWatchSession.value = false
                _activeRecording.value = if (rec.recordingId != null) rec else null
                _activeHLSSessionId.value = sessionId
                startHLSHeartbeat(sessionId)
                _playbackMode.value = PlaybackMode.ServerTranscodedHls
                playerEngine.loadMedia(
                    url = playlistURL,
                    isLive = true,
                    isSeekable = false,
                    headers = hlsAuthHeaders(),
                    title = mediaTitle,
                    artworkUrl = artworkUrl ?: rec.imageUrl
                )
                if (rec.recordingId != null) {
                    loadRecordingMetadata(rec)
                }
            } catch (e: Exception) {
                Log.player.error("Direct HLS channel stream failed: ${e.localizedMessage}")
                setPlaybackError(e)
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

            if (syncPlayClient.isConnected.value && syncPlayClient.isHost.value) {
                syncPlayClient.changeContent(
                    SyncPlayContent(
                        type = "recording",
                        id = recording.recordingId ?: "",
                        title = recording.title,
                        channelNumber = recording.channelNumber,
                        playUrl = recording.playUrl
                    )
                )
            }

            val baseURL = apiClient.baseURL
            val playUrl = recording.playUrl ?: return@launch

            val initialDur = recording.durationSeconds?.takeIf { it > 0 }
                ?: if (recording.start != null && recording.recordEnd != null && recording.recordEnd > recording.start) {
                    recording.recordEnd - recording.start
                } else null

            try {
                val hlsSession = apiClient.createRecordingHLSSession(
                    url = playUrl,
                    recordingId = recording.recordingId,
                    provider = recording.provider,
                    forCast = playerEngine.isCasting.value
                )
                val playlistURL = StreamURLBuilder.resolve(baseURL, hlsSession.playlistUrl)
                _activeHLSSessionId.value = hlsSession.sessionId
                startHLSHeartbeat(hlsSession.sessionId)
                _playbackMode.value = PlaybackMode.ServerTranscodedHls
                playerEngine.loadMedia(
                    url = playlistURL,
                    isLive = recording.isInProgress,
                    isSeekable = true,
                    initialDuration = initialDur,
                    headers = hlsAuthHeaders(),
                    title = recording.title,
                    artworkUrl = recording.imageUrl
                )
                loadRecordingMetadata(recording)
            } catch (e: Exception) {
                Log.player.error("Recording HLS stream failed: ${e.localizedMessage}")
                setPlaybackError(e)
            }
        }
    }

    private fun setPlaybackError(e: Throwable) {
        val parsed = PlaybackErrorMapper.mapApiError(e)
        playerEngine.setFailed(
            message = parsed.message,
            detail = parsed.detail,
            statusCode = parsed.statusCode,
            isNetworkError = parsed.isNetworkError
        )
    }

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

    fun selectAudioTrack(track: HDHomeRunRecordingAudioInfo) {
        // Audio track selection is baked into the HLS packaging itself
        // (backend maps a specific source audio stream via ffmpeg's `-map`
        // when building the session) rather than exposed as switchable
        // in-stream tracks on the produced playlist, so "switching"
        // requires starting a new HLS session with the new audio index
        // and resuming playback at the current position.
        if (_isSwitchingAudioTrack.value || track.index == playerEngine.currentAudioTrack.value?.index) return

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
                val recording = _activeRecording.value
                val channel = _activeChannel.value

                val (sessionId, playlistUrl) = when {
                    recording?.playUrl?.isNotEmpty() == true -> {
                        val session = apiClient.createRecordingHLSSession(
                            url = recording.playUrl,
                            recordingId = recording.recordingId,
                            start = resumeTime,
                            audioIndex = track.index,
                            provider = recording.provider,
                            forCast = playerEngine.isCasting.value
                        )
                        session.sessionId to session.playlistUrl
                    }
                    channel != null -> {
                        val session = apiClient.createChannelHLSSession(
                            channelNumber = channel.channelNumber,
                            forCast = playerEngine.isCasting.value,
                            audioIndex = track.index
                        )
                        (session.sessionId ?: return@launch) to (session.playUrl ?: return@launch)
                    }
                    else -> return@launch
                }

                val playlistURL = StreamURLBuilder.resolve(baseURL, playlistUrl)
                _activeHLSSessionId.value = sessionId
                startHLSHeartbeat(sessionId)
                // loadMedia() calls reset() internally, which wipes the audio
                // track list/video specs - restore them with the selected track atomically.
                playerEngine.loadMedia(
                    url = playlistURL,
                    isLive = isLive,
                    isSeekable = isSeekable,
                    headers = hlsAuthHeaders(),
                    title = recording?.title ?: channel?.name,
                    artworkUrl = recording?.imageUrl
                )
                playerEngine.setAudioTracks(previousAudioTracks, selectedTrack = track)
                playerEngine.setVideoSpecs(previousVideoSpecs)
                playerEngine.setTranscodeInfo(previousTranscodeInfo)

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
                _transientError.value = "Failed to switch audio track: ${e.localizedMessage ?: "Unknown error"}"
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
            liveCaptionAligner.lastRawCues = cues
            val aligned = liveCaptionAligner.alignLiveCues(recording, cues, playerEngine.currentTime.value)
            captionController.setCues(aligned)
        } catch (e: Exception) {
            // Captions are optional / not extracted yet - poller (if running) retries next tick
        }
    }

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

    private fun seekRecordingViaServer(recording: HDHomeRunRecording, playUrl: String, targetSeconds: Double) {
        serverSeekJob?.cancel()

        val previousSessionId = _activeHLSSessionId.value
        val previousAudioTracks = playerEngine.availableAudioTracks.value
        val previousTrack = playerEngine.currentAudioTrack.value
        val previousVideoSpecs = playerEngine.videoSpecs.value
        val previousTranscodeInfo = playerEngine.transcodeInfo.value
        val totalDuration = if (playerEngine.duration.value > 0) playerEngine.duration.value else (recording.durationSeconds ?: 0.0)
        val isLive = recording.isInProgress
        val isSeekable = playerEngine.isSeekable.value

        // Update position and pause playback without seeking the out-of-range old item
        playerEngine.prepareForServerSeek(targetSeconds)

        serverSeekJob = viewModelScope.launch {
            val baseURL = apiClient.baseURL
            try {
                val hlsSession = apiClient.createRecordingHLSSession(
                    url = playUrl,
                    recordingId = recording.recordingId,
                    start = targetSeconds,
                    audioIndex = previousTrack?.index,
                    provider = recording.provider,
                    forCast = playerEngine.isCasting.value
                )
                if (!isActive) {
                    viewModelScope.launch(NonCancellable) {
                        try {
                            apiClient.stopHLSSession(hlsSession.sessionId)
                        } catch (e: Exception) {
                            // Ignore
                        }
                    }
                    return@launch
                }
                val playlistURL = StreamURLBuilder.resolve(baseURL, hlsSession.playlistUrl)
                _activeHLSSessionId.value = hlsSession.sessionId
                startHLSHeartbeat(hlsSession.sessionId)

                playerEngine.loadMedia(
                    url = playlistURL,
                    isLive = isLive,
                    isSeekable = isSeekable,
                    initialDuration = totalDuration,
                    initialTimeOffset = targetSeconds,
                    headers = hlsAuthHeaders(),
                    title = recording.title,
                    artworkUrl = recording.imageUrl
                )
                playerEngine.setAudioTracks(previousAudioTracks, selectedTrack = previousTrack)
                playerEngine.setVideoSpecs(previousVideoSpecs)
                playerEngine.setTranscodeInfo(previousTranscodeInfo)

                if (previousSessionId != null) {
                    viewModelScope.launch(NonCancellable) {
                        try {
                            apiClient.stopHLSSession(previousSessionId)
                        } catch (e: Exception) {
                            // Ignore
                        }
                    }
                }
            } catch (e: Exception) {
                if (isActive) {
                    Log.player.error("Server seek failed: ${e.localizedMessage}")
                }
            }
        }
    }

    fun skipForward(seconds: Double = 10.0) {
        val target = playerEngine.currentTime.value + seconds
        seek(target)
    }

    fun skipBackward(seconds: Double = 10.0) {
        val target = (playerEngine.currentTime.value - seconds).coerceAtLeast(0.0)
        seek(target)
    }

    fun createSyncPlayRoom(userName: String, onComplete: ((Result<SyncPlayRoom>) -> Unit)? = null) {
        viewModelScope.launch {
            try {
                val content = currentSyncPlayContent() ?: SyncPlayContent(type = "channel", id = "")
                val resp = apiClient.createSyncPlayRoom(content = content, userName = userName)
                val wsUrl = apiClient.syncPlayWsUrl(resp.room.roomCode, userName)
                syncPlayClient.connect(wsUrl)
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
                syncPlayClient.connect(wsUrl)
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

    private fun resyncCaptionsAfterSeek() {
        val recording = _activeRecording.value ?: return
        val resynced = liveCaptionAligner.resyncCaptionsAfterSeek(recording, playerEngine.currentTime.value)
        if (resynced != null) {
            captionController.setCues(resynced)
        }
    }

    private fun startCaptionPolling(recording: HDHomeRunRecording) {
        if (!recording.isInProgress) return
        captionPollJob?.cancel()
        captionPollJob = viewModelScope.launch {
            while (isActive) {
                delay(CAPTION_POLL_INTERVAL_MS)
                val current = _activeRecording.value ?: break
                val wasInProgress = current.isInProgress
                if (!wasInProgress) {
                    fetchCaptionsOnce(current)
                    break
                }
                val start = current.start
                if (start != null) {
                    val elapsed = (System.currentTimeMillis() / 1000.0) - start
                    if (elapsed > playerEngine.duration.value) {
                        playerEngine.setDuration(elapsed)
                    }
                }
                fetchCaptionsOnce(current)
            }
        }
    }

    private fun stopCaptionPolling() {
        captionPollJob?.cancel()
        captionPollJob = null
    }

    fun closePlayer() {
        serverSeekJob?.cancel()
        serverSeekJob = null
        stopHLSHeartbeat()
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
    }
}
