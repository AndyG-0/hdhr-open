package org.hdhropen.kit.viewmodels

import androidx.lifecycle.viewModelScope
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIError
import org.hdhropen.kit.playback.*
import org.hdhropen.kit.utilities.Log

// Polling interval for the in-progress-recording caption refresh loop,
// split out of PlayerViewModel.kt's companion object since startCaptionPolling()
// is its only user and now lives in this file.
private const val CAPTION_POLL_INTERVAL_MS = 1_500L

// HLS session negotiation (channel/recording playback start, quality and
// audio-track switches, server-side seeking, and the metadata/captions that
// come with a recording), split out of PlayerViewModel.kt to keep that class
// under detekt's LargeClass cap. All the StateFlow backing properties these
// functions touch remain stored properties on PlayerViewModel itself
// (extension functions can't add stored properties).

@UnstableApi
internal fun PlayerViewModel.startHLSHeartbeat(sessionId: String) {
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

@UnstableApi
internal fun PlayerViewModel.stopHLSHeartbeat() {
    hlsHeartbeatJob?.cancel()
    hlsHeartbeatJob = null
}

@UnstableApi
fun PlayerViewModel.playChannel(channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry? = null) {
    viewModelScope.launch {
        closePlayer()
        initializeQualityForNewSession()
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
                    forCast = forCast,
                    quality = autoEffectiveTier.backendValue
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
                maybeStartAutoQualityPolling()
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
            val rec = apiClient.createChannelHLSSession(channel.channelNumber, forCast = forCast, quality = autoEffectiveTier.backendValue)
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
            maybeStartAutoQualityPolling()
        } catch (e: Exception) {
            Log.player.error("Direct HLS channel stream failed: ${e.localizedMessage}")
            setPlaybackError(e)
        }
    }
}

@UnstableApi
fun PlayerViewModel.playRecording(recording: HDHomeRunRecording) {
    viewModelScope.launch {
        closePlayer()
        initializeQualityForNewSession()
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
                forCast = playerEngine.isCasting.value,
                quality = autoEffectiveTier.backendValue
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
            maybeStartAutoQualityPolling()
        } catch (e: Exception) {
            Log.player.error("Recording HLS stream failed: ${e.localizedMessage}")
            setPlaybackError(e)
        }
    }
}

@UnstableApi
private fun PlayerViewModel.setPlaybackError(e: Throwable) {
    val parsed = PlaybackErrorMapper.mapApiError(e)
    playerEngine.setFailed(
        message = parsed.message,
        detail = parsed.detail,
        statusCode = parsed.statusCode,
        isNetworkError = parsed.isNetworkError
    )
}

@UnstableApi
fun PlayerViewModel.selectAudioTrack(track: HDHomeRunRecordingAudioInfo) {
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

// The actual session-swap: follows the exact template of
// selectAudioTrack() (new HLS session at the new quality, resume
// position, restore engine state, stop the old session in the
// background), just keyed on `quality` instead of `audioIndex`, and
// preserving the current audio track selection across the swap. Not
// private: called from PlayerViewModel.kt's selectQuality() and
// PlayerViewModel+AutoQuality.kt's applyAutoAdjustment().
@UnstableApi
internal fun PlayerViewModel.switchToQuality(backendValue: String?) {
    if (_isSwitchingQuality.value) return
    viewModelScope.launch {
        _isSwitchingQuality.value = true
        try {
            val resumeTime = playerEngine.currentTime.value
            val isLive = playerEngine.isLive.value
            val isSeekable = playerEngine.isSeekable.value
            val previousSessionId = _activeHLSSessionId.value
            val previousAudioTracks = playerEngine.availableAudioTracks.value
            val previousTrack = playerEngine.currentAudioTrack.value
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
                        audioIndex = previousTrack?.index,
                        provider = recording.provider,
                        forCast = playerEngine.isCasting.value,
                        quality = backendValue
                    )
                    session.sessionId to session.playlistUrl
                }
                channel != null -> {
                    val session = apiClient.createChannelHLSSession(
                        channelNumber = channel.channelNumber,
                        forCast = playerEngine.isCasting.value,
                        audioIndex = previousTrack?.index,
                        quality = backendValue
                    )
                    (session.sessionId ?: return@launch) to (session.playUrl ?: return@launch)
                }
                else -> return@launch
            }

            val playlistURL = StreamURLBuilder.resolve(baseURL, playlistUrl)
            _activeHLSSessionId.value = sessionId
            startHLSHeartbeat(sessionId)
            playerEngine.loadMedia(
                url = playlistURL,
                isLive = isLive,
                isSeekable = isSeekable,
                headers = hlsAuthHeaders(),
                title = recording?.title ?: channel?.name,
                artworkUrl = recording?.imageUrl
            )
            playerEngine.setAudioTracks(previousAudioTracks, selectedTrack = previousTrack)
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
            Log.player.error("Quality switch failed: ${e.localizedMessage}")
            _transientError.value = "Failed to switch quality: ${e.localizedMessage ?: "Unknown error"}"
        } finally {
            _isSwitchingQuality.value = false
        }
    }
}

@UnstableApi
private fun PlayerViewModel.hlsAuthHeaders(): Map<String, String> =
    apiClient.bearerToken?.let { mapOf("Authorization" to "Bearer $it") } ?: emptyMap()

@UnstableApi
private fun PlayerViewModel.loadRecordingMetadata(recording: HDHomeRunRecording) {
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
            playerEngine.setCommercialSegments(detail.commercialSegments)
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

@UnstableApi
private suspend fun PlayerViewModel.fetchCaptionsOnce(recording: HDHomeRunRecording) {
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

// Called from PlayerViewModel.kt's seek() when the target position falls
// outside the current HLS session's seekable range. Not private: cross-file.
@UnstableApi
internal fun PlayerViewModel.seekRecordingViaServer(recording: HDHomeRunRecording, playUrl: String, targetSeconds: Double) {
    serverSeekJob?.cancel()

    val previousSessionId = _activeHLSSessionId.value
    val previousAudioTracks = playerEngine.availableAudioTracks.value
    val previousTrack = playerEngine.currentAudioTrack.value
    val previousVideoSpecs = playerEngine.videoSpecs.value
    val previousTranscodeInfo = playerEngine.transcodeInfo.value
    val previousCommercialSegments = playerEngine.commercialSegments.value
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
            playerEngine.setCommercialSegments(previousCommercialSegments)

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

// Called from PlayerViewModel.kt's seek(). Not private: cross-file.
@UnstableApi
internal fun PlayerViewModel.resyncCaptionsAfterSeek() {
    val recording = _activeRecording.value ?: return
    val resynced = liveCaptionAligner.resyncCaptionsAfterSeek(recording, playerEngine.currentTime.value)
    if (resynced != null) {
        captionController.setCues(resynced)
    }
}

@UnstableApi
private fun PlayerViewModel.startCaptionPolling(recording: HDHomeRunRecording) {
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

// Called from PlayerViewModel.kt's closePlayer(). Not private: cross-file.
@UnstableApi
internal fun PlayerViewModel.stopCaptionPolling() {
    captionPollJob?.cancel()
    captionPollJob = null
}
