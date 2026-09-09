package org.hdhropen.kit.playback

import android.content.Context
import android.net.Uri
import androidx.media3.cast.CastPlayer
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.analytics.AnalyticsListener
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.datasource.HttpDataSource
import com.google.android.gms.cast.framework.CastContext
import com.google.android.gms.cast.framework.CastSession
import com.google.android.gms.cast.framework.SessionManagerListener
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.hdhropen.kit.models.HDHomeRunRecordingAudioInfo
import org.hdhropen.kit.models.HDHomeRunRecordingVideoInfo
import org.hdhropen.kit.models.HDHomeRunTranscodeInfo
import org.hdhropen.kit.utilities.Log

sealed class PlaybackState {
    object Idle : PlaybackState()
    object Loading : PlaybackState()
    object Playing : PlaybackState()
    object Paused : PlaybackState()
    object Buffering : PlaybackState()
    data class Failed(
        val message: String,
        val detail: String? = null,
        val statusCode: Int? = null,
        val isNetworkError: Boolean = false
    ) : PlaybackState()
}

data class ParsedPlaybackError(
    val message: String,
    val detail: String? = null,
    val statusCode: Int? = null,
    val isNetworkError: Boolean = false
)

internal fun extractDetailFromBody(bytes: ByteArray): String? {
    if (bytes.isEmpty()) return null
    return try {
        val text = String(bytes, Charsets.UTF_8).trim()
        if (text.startsWith("{")) {
            val root = Json { ignoreUnknownKeys = true }.parseToJsonElement(text)
            root.jsonObject["detail"]?.jsonPrimitive?.contentOrNull
        } else if (!text.startsWith("<") && text.length < 300) {
            text
        } else {
            null
        }
    } catch (e: Exception) {
        null
    }
}

internal fun parseExoPlayerError(error: PlaybackException): ParsedPlaybackError {
    var cur: Throwable? = error
    var httpException: HttpDataSource.InvalidResponseCodeException? = null
    var networkException: HttpDataSource.HttpDataSourceException? = null

    while (cur != null) {
        if (cur is HttpDataSource.InvalidResponseCodeException) {
            httpException = cur
            break
        }
        if (cur is HttpDataSource.HttpDataSourceException && networkException == null) {
            networkException = cur
        }
        cur = cur.cause
    }

    if (httpException != null) {
        val code = httpException.responseCode
        val serverDetail = extractDetailFromBody(httpException.responseBody)

        return when (code) {
            502 -> ParsedPlaybackError(
                message = "Tuner or streaming server temporarily unavailable (HTTP 502)",
                detail = serverDetail ?: "The streaming server or HDHomeRun tuner reported a temporary failure. Try again in a few moments.",
                statusCode = 502,
                isNetworkError = true
            )
            503 -> ParsedPlaybackError(
                message = "Streaming service unavailable (HTTP 503)",
                detail = serverDetail ?: "The server is temporarily busy or unavailable. Please try again shortly.",
                statusCode = 503,
                isNetworkError = true
            )
            504 -> ParsedPlaybackError(
                message = "Stream gateway timeout (HTTP 504)",
                detail = serverDetail ?: "The server timed out waiting for the tuner or transcoder.",
                statusCode = 504,
                isNetworkError = true
            )
            404 -> ParsedPlaybackError(
                message = "Stream session not found (HTTP 404)",
                detail = serverDetail ?: "The live watch session or recording stream has ended or expired.",
                statusCode = 404,
                isNetworkError = true
            )
            401, 403 -> ParsedPlaybackError(
                message = "Authentication error (HTTP $code)",
                detail = serverDetail ?: "Your session is invalid or expired. Please sign in again.",
                statusCode = code,
                isNetworkError = true
            )
            else -> ParsedPlaybackError(
                message = "Server error (HTTP $code)",
                detail = serverDetail ?: "The server returned HTTP status code $code.",
                statusCode = code,
                isNetworkError = true
            )
        }
    }

    if (networkException != null) {
        val rootCause = networkException.cause
        val detail = when (rootCause) {
            is java.net.ConnectException -> "Could not connect to the streaming server. Verify the server is running."
            is java.net.SocketTimeoutException -> "The connection to the streaming server timed out."
            is java.net.UnknownHostException -> "Could not resolve the server hostname."
            else -> networkException.message ?: "Failed to read data from the server."
        }
        return ParsedPlaybackError(
            message = "Network connection error",
            detail = detail,
            statusCode = null,
            isNetworkError = true
        )
    }

    if (error.errorCode == PlaybackException.ERROR_CODE_DECODER_INIT_FAILED) {
        return ParsedPlaybackError(
            message = "Video decoder error",
            detail = "Unable to initialize video decoder for this broadcast format.",
            statusCode = null,
            isNetworkError = false
        )
    }

    val cleanMsg = error.localizedMessage
        ?.takeIf { !it.contains("androidx.media3") && !it.contains("Exception") }
        ?: "An unexpected playback error occurred."

    return ParsedPlaybackError(
        message = "Playback error",
        detail = cleanMsg,
        statusCode = null,
        isNetworkError = false
    )
}

@UnstableApi
class PlayerEngine(
    private val context: Context? = null,
    private val coroutineScope: CoroutineScope = CoroutineScope(Dispatchers.Main + SupervisorJob())
) {
    private val _state = MutableStateFlow<PlaybackState>(PlaybackState.Idle)
    val state: StateFlow<PlaybackState> = _state.asStateFlow()

    private val _currentTime = MutableStateFlow(0.0)
    val currentTime: StateFlow<Double> = _currentTime.asStateFlow()

    var timeOffset: Double = 0.0
        private set

    private val _duration = MutableStateFlow(0.0)
    val duration: StateFlow<Double> = _duration.asStateFlow()

    private val _isLive = MutableStateFlow(false)
    val isLive: StateFlow<Boolean> = _isLive.asStateFlow()

    private val _isSeekable = MutableStateFlow(false)
    val isSeekable: StateFlow<Boolean> = _isSeekable.asStateFlow()

    private val _availableAudioTracks = MutableStateFlow<List<HDHomeRunRecordingAudioInfo>>(emptyList())
    val availableAudioTracks: StateFlow<List<HDHomeRunRecordingAudioInfo>> = _availableAudioTracks.asStateFlow()

    private val _currentAudioTrack = MutableStateFlow<HDHomeRunRecordingAudioInfo?>(null)
    val currentAudioTrack: StateFlow<HDHomeRunRecordingAudioInfo?> = _currentAudioTrack.asStateFlow()

    private val _videoSpecs = MutableStateFlow<HDHomeRunRecordingVideoInfo?>(null)
    val videoSpecs: StateFlow<HDHomeRunRecordingVideoInfo?> = _videoSpecs.asStateFlow()

    private val _transcodeInfo = MutableStateFlow<HDHomeRunTranscodeInfo?>(null)
    val transcodeInfo: StateFlow<HDHomeRunTranscodeInfo?> = _transcodeInfo.asStateFlow()

    private val _observedBitrateBps = MutableStateFlow<Long?>(null)
    val observedBitrateBps: StateFlow<Long?> = _observedBitrateBps.asStateFlow()

    private val _isCasting = MutableStateFlow(false)
    val isCasting: StateFlow<Boolean> = _isCasting.asStateFlow()

    var exoPlayer: ExoPlayer? = null
        private set

    // Typed as the common Player interface (not the concrete CastPlayer
    // class) even though it's always a CastPlayer at runtime: CastPlayer's
    // static initializer touches android.util.SparseBooleanArray, which is
    // an unmocked stub in this module's plain-JUnit (no Robolectric) tests,
    // so mockk can't proxy the concrete class there. Every call site here
    // only needs Player-interface methods, so this costs nothing.
    var castPlayer: Player? = null
        private set

    private var castContext: CastContext? = null
    private var sessionManagerListener: SessionManagerListener<CastSession>? = null

    // Routes every playback control call to whichever player is currently
    // presenting media - ExoPlayer for local playback, CastPlayer once a
    // Cast session is connected - so callers never branch on isCasting
    // themselves.
    private val activePlayer: Player?
        get() = if (_isCasting.value) castPlayer else exoPlayer

    private var timeTrackingJob: Job? = null

    init {
        context?.let { ctx ->
            exoPlayer = ExoPlayer.Builder(ctx).build().apply {
                playWhenReady = true
                addListener(createPlayerListener())
                addAnalyticsListener(createBandwidthListener())
            }

            // CastContext.getSharedInstance can throw when Play Services is
            // missing/outdated on the device (common on some Android TV
            // boxes/emulators) - swallow so Cast support degrades to
            // "unavailable" instead of crashing local playback.
            runCatching { CastContext.getSharedInstance(ctx) }.getOrNull()?.let { sharedCastContext ->
                castContext = sharedCastContext
                castPlayer = CastPlayer(sharedCastContext).apply {
                    addListener(createPlayerListener())
                }
                val listener = createSessionManagerListener()
                sessionManagerListener = listener
                sharedCastContext.sessionManager.addSessionManagerListener(listener, CastSession::class.java)
            }
        }
    }

    private fun createSessionManagerListener() = object : SessionManagerListener<CastSession> {
        override fun onSessionStarted(session: CastSession, sessionId: String) {
            _isCasting.value = true
        }

        override fun onSessionResumed(session: CastSession, wasSuspended: Boolean) {
            _isCasting.value = true
        }

        override fun onSessionEnded(session: CastSession, error: Int) {
            _isCasting.value = false
        }

        override fun onSessionSuspended(session: CastSession, reason: Int) {
            _isCasting.value = false
        }

        override fun onSessionStarting(session: CastSession) {}
        override fun onSessionStartFailed(session: CastSession, error: Int) {}
        override fun onSessionEnding(session: CastSession) {}
        override fun onSessionResuming(session: CastSession, sessionId: String) {}
        override fun onSessionResumeFailed(session: CastSession, error: Int) {}
    }

    private fun createBandwidthListener() = object : AnalyticsListener {
        override fun onBandwidthEstimate(
            eventTime: AnalyticsListener.EventTime,
            totalLoadTimeMs: Int,
            totalBytesLoaded: Long,
            bitrateEstimate: Long
        ) {
            // ExoPlayer-only signal - naturally stops updating while casting
            // since ExoPlayer isn't loading anything, so no isCasting guard
            // is needed here.
            _observedBitrateBps.value = bitrateEstimate
        }
    }

    private fun createPlayerListener() = object : Player.Listener {
        override fun onPlaybackStateChanged(playbackState: Int) {
            when (playbackState) {
                Player.STATE_IDLE -> {
                    // Stay in current or idle
                }
                Player.STATE_BUFFERING -> {
                    _state.value = PlaybackState.Buffering
                }
                Player.STATE_READY -> {
                    val dur = activePlayer?.duration ?: 0L
                    if (dur > 0 && dur != androidx.media3.common.C.TIME_UNSET) {
                        val durSec = timeOffset + (dur / 1000.0)
                        if (_duration.value <= 0.0 || durSec > _duration.value) {
                            _duration.value = durSec
                        }
                    }
                    _state.value = if (activePlayer?.playWhenReady == true) PlaybackState.Playing else PlaybackState.Paused
                }
                Player.STATE_ENDED -> {
                    _state.value = PlaybackState.Paused
                }
            }
        }

        override fun onTimelineChanged(timeline: androidx.media3.common.Timeline, reason: Int) {
            activePlayer?.let { player ->
                val dur = player.duration
                if (dur > 0 && dur != androidx.media3.common.C.TIME_UNSET) {
                    val durSec = timeOffset + (dur / 1000.0)
                    if (_duration.value <= 0.0 || durSec > _duration.value) {
                        _duration.value = durSec
                    }
                }
            }
        }

        override fun onIsPlayingChanged(isPlaying: Boolean) {
            if (isPlaying) {
                _state.value = PlaybackState.Playing
                startTimeTracking()
            } else if (_state.value != PlaybackState.Buffering && _state.value !is PlaybackState.Failed) {
                _state.value = PlaybackState.Paused
                stopTimeTracking()
            }
        }

        override fun onPlayerError(error: PlaybackException) {
            if (error.errorCode == PlaybackException.ERROR_CODE_BEHIND_LIVE_WINDOW) {
                Log.player.warning("Fell behind live window, seeking to live default position and restarting")
                exoPlayer?.seekToDefaultPosition()
                exoPlayer?.prepare()
                return
            }
            val parsed = parseExoPlayerError(error)
            _state.value = PlaybackState.Failed(
                message = parsed.message,
                detail = parsed.detail,
                statusCode = parsed.statusCode,
                isNetworkError = parsed.isNetworkError
            )
            Log.player.error("ExoPlayer error (status=${parsed.statusCode}, network=${parsed.isNetworkError}): ${parsed.message} - ${parsed.detail}", error)
            stopTimeTracking()
        }
    }

    private fun buildMediaItem(url: String, title: String?, artworkUrl: String?): MediaItem {
        val mediaMetadata = MediaMetadata.Builder().apply {
            title?.let { setTitle(it) }
            artworkUrl?.let { setArtworkUri(Uri.parse(it)) }
        }.build()
        return MediaItem.Builder()
            .setUri(Uri.parse(url))
            .setMediaMetadata(mediaMetadata)
            .build()
    }

    fun loadMedia(
        url: String,
        isLive: Boolean = false,
        isSeekable: Boolean = true,
        initialStart: Double? = null,
        initialDuration: Double? = null,
        initialTimeOffset: Double = 0.0,
        headers: Map<String, String> = emptyMap(),
        title: String? = null,
        artworkUrl: String? = null
    ) {
        reset()
        _isLive.value = isLive
        _isSeekable.value = isSeekable
        timeOffset = initialTimeOffset
        if (initialDuration != null && initialDuration > 0) {
            _duration.value = initialDuration
        }
        _currentTime.value = initialTimeOffset + (initialStart ?: 0.0)
        _state.value = PlaybackState.Loading

        // The player-null early-returns below must happen before Uri.parse()
        // is ever called - a PlayerEngine built without a Context (as in
        // JVM unit tests) never constructs exoPlayer/castPlayer, and
        // android.net.Uri is an unmocked stub jar method in that setup, so
        // building a MediaItem before knowing there's a player to hand it to
        // would fail tests that construct PlayerEngine(context = null) and
        // call loadMedia() as a deliberate no-op.
        if (_isCasting.value) {
            // CastPlayer takes MediaItems directly - the receiver fetches the
            // playlist itself over its own network stack, so ExoPlayer's
            // HLS/Progressive MediaSource plumbing and custom auth headers
            // (which the receiver can't attach anyway) don't apply here. The
            // caller is responsible for passing a URL the Cast receiver can
            // reach and authenticate on its own (the cast-token-scoped
            // playlist URL), not a reconstructed native session URL.
            val player = castPlayer ?: return
            val mediaItem = buildMediaItem(url, title, artworkUrl)
            player.setMediaItems(listOf(mediaItem))
            if (initialStart != null && initialStart > 0) {
                player.seekTo((initialStart * 1000).toLong())
            }
            player.prepare()
            player.play()
            startTimeTracking()
            return
        }

        val player = exoPlayer ?: return
        val mediaItem = buildMediaItem(url, title, artworkUrl)

        // ExoPlayer issues playlist/segment requests through its own HTTP
        // stack, which never goes through APIClient - headers must be
        // attached here to authenticate them, mirroring PlayerEngine.swift's
        // AVURLAssetHTTPHeaderFieldsKey workaround for AVPlayer.
        val httpDataSourceFactory = DefaultHttpDataSource.Factory().apply {
            if (headers.isNotEmpty()) setDefaultRequestProperties(headers)
        }
        val dataSourceFactory = DefaultDataSource.Factory(context ?: return, httpDataSourceFactory)

        if (url.contains(".m3u8")) {
            val mediaSource = HlsMediaSource.Factory(dataSourceFactory).createMediaSource(mediaItem)
            player.setMediaSource(mediaSource)
        } else {
            val mediaSource = ProgressiveMediaSource.Factory(dataSourceFactory).createMediaSource(mediaItem)
            player.setMediaSource(mediaSource)
        }

        if (initialStart != null && initialStart > 0) {
            player.seekTo((initialStart * 1000).toLong())
        }

        player.prepare()
        player.play()
        startTimeTracking()
    }

    fun play() {
        activePlayer?.play()
        if (_state.value == PlaybackState.Paused) {
            _state.value = PlaybackState.Playing
            startTimeTracking()
        }
    }

    fun pause() {
        activePlayer?.pause()
        if (_state.value == PlaybackState.Playing) {
            _state.value = PlaybackState.Paused
            stopTimeTracking()
        }
    }

    fun togglePlayPause() {
        if (_state.value == PlaybackState.Playing) {
            pause()
        } else if (_state.value == PlaybackState.Paused) {
            play()
        }
    }

    fun seek(seconds: Double) {
        if (!_isSeekable.value) return
        val dur = if (_duration.value > 0) _duration.value else seconds
        val target = seconds.coerceIn(0.0, dur)
        val relativeSeconds = (target - timeOffset).coerceAtLeast(0.0)
        activePlayer?.seekTo((relativeSeconds * 1000).toLong())
        _currentTime.value = target
    }

    fun isPositionInSeekableRange(seconds: Double): Boolean {
        if (!_isSeekable.value) return false
        val player = activePlayer ?: return false
        val relativeSeconds = seconds - timeOffset
        if (relativeSeconds < 0.0) return false

        val timeline = player.currentTimeline
        if (timeline.isEmpty) return false
        val window = androidx.media3.common.Timeline.Window()
        timeline.getWindow(player.currentMediaItemIndex, window)
        if (!window.isSeekable) return false

        val durMs = if (window.durationMs > 0 && window.durationMs != androidx.media3.common.C.TIME_UNSET) {
            window.durationMs
        } else {
            player.duration.takeIf { it > 0 && it != androidx.media3.common.C.TIME_UNSET } ?: 0L
        }
        if (durMs <= 0) return false
        val end = durMs / 1000.0
        val effectiveEnd = (end - 0.5).coerceAtLeast(0.0)
        return relativeSeconds <= effectiveEnd
    }

    fun prepareForServerSeek(targetSeconds: Double) {
        val dur = if (_duration.value > 0) _duration.value else targetSeconds
        val clamped = targetSeconds.coerceIn(0.0, dur)
        _currentTime.value = clamped
        activePlayer?.pause()
        _state.value = PlaybackState.Buffering
    }

    fun skipForward(seconds: Double = 10.0) {
        seek(_currentTime.value + seconds)
    }

    fun skipBackward(seconds: Double = 10.0) {
        seek((_currentTime.value - seconds).coerceAtLeast(0.0))
    }

    fun setAudioTracks(tracks: List<HDHomeRunRecordingAudioInfo>, selectedTrack: HDHomeRunRecordingAudioInfo? = null) {
        _availableAudioTracks.value = tracks
        if (selectedTrack != null) {
            _currentAudioTrack.value = selectedTrack
        } else if (_currentAudioTrack.value == null && tracks.isNotEmpty()) {
            _currentAudioTrack.value = tracks.first()
        }
    }

    fun selectAudioTrack(track: HDHomeRunRecordingAudioInfo) {
        _currentAudioTrack.value = track
    }

    fun setVideoSpecs(specs: HDHomeRunRecordingVideoInfo?) {
        _videoSpecs.value = specs
    }

    fun setTranscodeInfo(info: HDHomeRunTranscodeInfo?) {
        _transcodeInfo.value = info
    }

    fun setDuration(dur: Double) {
        _duration.value = dur
    }

    fun setSeekable(seekable: Boolean) {
        _isSeekable.value = seekable
    }

    fun setFailed(
        message: String,
        detail: String? = null,
        statusCode: Int? = null,
        isNetworkError: Boolean = false
    ) {
        _state.value = PlaybackState.Failed(message, detail, statusCode, isNetworkError)
        stopTimeTracking()
    }

    fun setPlaybackSpeed(speed: Float) {
        activePlayer?.setPlaybackSpeed(speed)
    }

    fun reset() {
        stopTimeTracking()
        exoPlayer?.stop()
        exoPlayer?.clearMediaItems()
        castPlayer?.stop()
        castPlayer?.clearMediaItems()

        _state.value = PlaybackState.Idle
        _currentTime.value = 0.0
        timeOffset = 0.0
        _duration.value = 0.0
        _isLive.value = false
        _isSeekable.value = false
        _availableAudioTracks.value = emptyList()
        _currentAudioTrack.value = null
        _videoSpecs.value = null
        _transcodeInfo.value = null
        _observedBitrateBps.value = null
    }

    private fun startTimeTracking() {
        timeTrackingJob?.cancel()
        timeTrackingJob = coroutineScope.launch(Dispatchers.Main) {
            while (isActive) {
                delay(500)
                activePlayer?.let { player ->
                    val posMs = player.currentPosition
                    if (posMs >= 0) {
                        val currentSec = timeOffset + (posMs / 1000.0)
                        _currentTime.value = currentSec
                        if (_isLive.value && currentSec > _duration.value) {
                            _duration.value = currentSec
                        }
                    }
                    val durMs = player.duration
                    if (durMs > 0 && durMs != androidx.media3.common.C.TIME_UNSET) {
                        val durSec = timeOffset + (durMs / 1000.0)
                        if (_duration.value <= 0.0 || durSec > _duration.value) {
                            _duration.value = durSec
                        }
                    }
                }
            }
        }
    }

    private fun stopTimeTracking() {
        timeTrackingJob?.cancel()
        timeTrackingJob = null
    }

    fun release() {
        reset()
        exoPlayer?.release()
        exoPlayer = null
        castPlayer?.release()
        castPlayer = null
        sessionManagerListener?.let { listener ->
            castContext?.sessionManager?.removeSessionManagerListener(listener, CastSession::class.java)
        }
        sessionManagerListener = null
        castContext = null
    }
}
