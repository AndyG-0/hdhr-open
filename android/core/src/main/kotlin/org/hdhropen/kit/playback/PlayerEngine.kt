package org.hdhropen.kit.playback

import android.content.Context
import android.net.Uri
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.hls.HlsMediaSource
import androidx.media3.datasource.DefaultDataSource
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.hdhropen.kit.models.HDHomeRunRecordingAudioInfo
import org.hdhropen.kit.models.HDHomeRunRecordingVideoInfo
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

    var exoPlayer: ExoPlayer? = null
        private set

    private var timeTrackingJob: Job? = null

    init {
        context?.let { ctx ->
            exoPlayer = ExoPlayer.Builder(ctx).build().apply {
                playWhenReady = true
                addListener(createPlayerListener())
            }
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
                    val dur = exoPlayer?.duration ?: 0L
                    if (dur > 0) {
                        _duration.value = dur / 1000.0
                    }
                    _state.value = if (exoPlayer?.playWhenReady == true) PlaybackState.Playing else PlaybackState.Paused
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

    fun loadMedia(url: String, isLive: Boolean = false, isSeekable: Boolean = true, initialStart: Double? = null) {
        reset()
        _isLive.value = isLive
        _isSeekable.value = isSeekable
        _state.value = PlaybackState.Loading

        val player = exoPlayer ?: return
        val uri = Uri.parse(url)

        val mediaItem = MediaItem.Builder()
            .setUri(uri)
            .build()

        if (url.contains(".m3u8")) {
            val dataSourceFactory = DefaultDataSource.Factory(player.applicationLooper.let { context ?: return })
            val mediaSource = HlsMediaSource.Factory(dataSourceFactory).createMediaSource(mediaItem)
            player.setMediaSource(mediaSource)
        } else {
            player.setMediaItem(mediaItem)
        }

        if (initialStart != null && initialStart > 0) {
            player.seekTo((initialStart * 1000).toLong())
        }

        player.prepare()
        player.play()
        startTimeTracking()
    }

    fun play() {
        exoPlayer?.play()
        if (_state.value == PlaybackState.Paused) {
            _state.value = PlaybackState.Playing
            startTimeTracking()
        }
    }

    fun pause() {
        exoPlayer?.pause()
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
        exoPlayer?.seekTo((target * 1000).toLong())
        _currentTime.value = target
    }

    fun skipForward(seconds: Double = 10.0) {
        seek(_currentTime.value + seconds)
    }

    fun skipBackward(seconds: Double = 10.0) {
        seek((_currentTime.value - seconds).coerceAtLeast(0.0))
    }

    fun setAudioTracks(tracks: List<HDHomeRunRecordingAudioInfo>) {
        _availableAudioTracks.value = tracks
        if (_currentAudioTrack.value == null && tracks.isNotEmpty()) {
            _currentAudioTrack.value = tracks.first()
        }
    }

    fun selectAudioTrack(track: HDHomeRunRecordingAudioInfo) {
        _currentAudioTrack.value = track
    }

    fun setVideoSpecs(specs: HDHomeRunRecordingVideoInfo?) {
        _videoSpecs.value = specs
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

        _state.value = PlaybackState.Idle
        _currentTime.value = 0.0
        _duration.value = 0.0
        _isLive.value = false
        _isSeekable.value = false
        _availableAudioTracks.value = emptyList()
        _currentAudioTrack.value = null
        _videoSpecs.value = null
    }

    private fun startTimeTracking() {
        timeTrackingJob?.cancel()
        timeTrackingJob = coroutineScope.launch(Dispatchers.Main) {
            while (isActive) {
                delay(500)
                exoPlayer?.let { player ->
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
    }
}
