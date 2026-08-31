package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
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

            // Fetch Captions VTT
            try {
                val capURL = StreamURLBuilder.captionsURL(
                    baseURL = baseURL,
                    recordingId = recId,
                    playUrl = playUrl,
                    recordEnd = recording.recordEnd,
                    provider = recording.provider
                )
                val capString = apiClient.fetchRawString(capURL)
                val cues = VTTParser.parseCaptions(capString)
                captionController.setCues(cues)
            } catch (e: Exception) {
                // Captions are optional
            }
        }
    }

    fun closePlayer() {
        playerEngine.reset()
        watchSessionManager.stopWatch()

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
