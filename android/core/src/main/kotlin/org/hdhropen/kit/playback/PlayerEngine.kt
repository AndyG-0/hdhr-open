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
import com.google.android.gms.cast.framework.CastContext
import com.google.android.gms.cast.framework.CastSession
import com.google.android.gms.cast.framework.SessionManagerListener
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
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
    data class Failed(val message: String) : PlaybackState()
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
                    if (dur > 0) {
                        _duration.value = dur / 1000.0
                    }
                    _state.value = if (activePlayer?.playWhenReady == true) PlaybackState.Playing else PlaybackState.Paused
                }
                Player.STATE_ENDED -> {
                    _state.value = PlaybackState.Paused
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
            val msg = error.localizedMessage ?: "Playback failed."
            _state.value = PlaybackState.Failed(msg)
            Log.player.error("ExoPlayer error: $msg", error)
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
        headers: Map<String, String> = emptyMap(),
        title: String? = null,
        artworkUrl: String? = null
    ) {
        reset()
        _isLive.value = isLive
        _isSeekable.value = isSeekable
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
        activePlayer?.seekTo((target * 1000).toLong())
        _currentTime.value = target
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

    fun setFailed(message: String) {
        _state.value = PlaybackState.Failed(message)
    }

    fun reset() {
        stopTimeTracking()
        exoPlayer?.stop()
        exoPlayer?.clearMediaItems()
        castPlayer?.stop()
        castPlayer?.clearMediaItems()

        _state.value = PlaybackState.Idle
        _currentTime.value = 0.0
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
                        _currentTime.value = posMs / 1000.0
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
