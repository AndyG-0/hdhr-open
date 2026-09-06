package org.hdhropen.app

import android.app.PictureInPictureParams
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Rect
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.content.ContextCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.navigation.RootMobileScreen
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.playback.PlaybackState
import org.hdhropen.kit.theme.ThemeMode
import org.hdhropen.kit.viewmodels.AppEnvironment

@UnstableApi
class MainActivity : ComponentActivity() {
    private lateinit var appEnvironment: AppEnvironment

    private val _isInPipMode = MutableStateFlow(false)
    val isInPipMode: StateFlow<Boolean> = _isInPipMode.asStateFlow()

    private var videoBounds: Rect? = null

    val isPipSupported: Boolean
        get() = packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)

    private val pipReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (!::appEnvironment.isInitialized) return
            when (intent?.action) {
                PipHelper.ACTION_PIP_PLAY -> {
                    if (appEnvironment.playerEngine.state.value is PlaybackState.Failed) {
                        appEnvironment.playerViewModel.retry()
                    } else {
                        appEnvironment.playerViewModel.play()
                    }
                }
                PipHelper.ACTION_PIP_PAUSE -> appEnvironment.playerViewModel.pause()
                PipHelper.ACTION_PIP_REWIND -> appEnvironment.playerViewModel.skipBackward(10.0)
                PipHelper.ACTION_PIP_FORWARD -> appEnvironment.playerViewModel.skipForward(10.0)
            }
        }
    }

    // When the whole app leaves the foreground, release the tuner if not in PiP.
    // Registered on ProcessLifecycleOwner (not this Activity) so it fires once per real
    // app-background transition rather than on every config change.
    private val processLifecycleObserver = object : DefaultLifecycleObserver {
        override fun onStop(owner: LifecycleOwner) {
            if (::appEnvironment.isInitialized && !_isInPipMode.value) {
                appEnvironment.playerViewModel.closePlayer()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        appEnvironment = AppEnvironment(applicationContext)
        ProcessLifecycleOwner.get().lifecycle.addObserver(processLifecycleObserver)

        // Register BroadcastReceiver for PiP remote actions
        val filter = IntentFilter().apply {
            addAction(PipHelper.ACTION_PIP_PLAY)
            addAction(PipHelper.ACTION_PIP_PAUSE)
            addAction(PipHelper.ACTION_PIP_REWIND)
            addAction(PipHelper.ACTION_PIP_FORWARD)
        }
        ContextCompat.registerReceiver(
            this,
            pipReceiver,
            filter,
            ContextCompat.RECEIVER_NOT_EXPORTED
        )

        lifecycleScope.launch {
            appEnvironment.authManager.restoreSession()
        }

        // Reactively update PiP parameters whenever playback state, seekable flag,
        // casting mode, or active media changes.
        lifecycleScope.launch {
            combine(
                appEnvironment.playerEngine.state,
                appEnvironment.playerEngine.isSeekable,
                appEnvironment.playerEngine.isCasting,
                appEnvironment.playerViewModel.activeChannel,
                appEnvironment.playerViewModel.activeRecording
            ) { _, _, _, _, _ ->
                // trigger
            }.collect {
                updatePipParams()
            }
        }

        setContent {
            val themeMode by appEnvironment.themePreferences.themeMode.collectAsState()
            val useDarkTheme = when (themeMode) {
                ThemeMode.LIGHT -> false
                ThemeMode.DARK -> true
                ThemeMode.SYSTEM -> isSystemInDarkTheme()
            }
            val inPip by _isInPipMode.collectAsState()

            LaunchedEffect(useDarkTheme) {
                WindowInsetsControllerCompat(window, window.decorView).isAppearanceLightStatusBars = !useDarkTheme
            }

            HDHROpenTheme(themeMode = themeMode) {
                RootMobileScreen(
                    appEnvironment = appEnvironment,
                    isInPipMode = inPip,
                    onEnterPip = { enterPip() },
                    onUpdateVideoBounds = { rect -> updateVideoBounds(rect) }
                )
            }
        }
    }

    fun updateVideoBounds(rect: Rect) {
        videoBounds = rect
        updatePipParams()
    }

    fun buildPipParams(): PictureInPictureParams {
        val builder = PictureInPictureParams.Builder()

        val isPlayerActive = appEnvironment.playerViewModel.activeChannel.value != null ||
            appEnvironment.playerViewModel.activeRecording.value != null
        val isPlaying = appEnvironment.playerEngine.state.value == PlaybackState.Playing
        val isSeekable = appEnvironment.playerEngine.isSeekable.value
        val isCasting = appEnvironment.playerEngine.isCasting.value

        val videoSpecs = appEnvironment.playerEngine.videoSpecs.value
        val exoVideoSize = appEnvironment.playerEngine.exoPlayer?.videoSize
        val width = videoSpecs?.width ?: exoVideoSize?.width
        val height = videoSpecs?.height ?: exoVideoSize?.height
        builder.setAspectRatio(PipHelper.calculateAspectRatio(width, height))

        videoBounds?.let { bounds ->
            if (!bounds.isEmpty && bounds.width() > 0 && bounds.height() > 0) {
                builder.setSourceRectHint(bounds)
            }
        }

        if (isPlayerActive && !isCasting) {
            builder.setActions(PipHelper.buildRemoteActions(this, isPlaying, isSeekable))
        } else {
            builder.setActions(emptyList())
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val canAutoEnter = isPlayerActive && isPlaying && !isCasting
            builder.setAutoEnterEnabled(canAutoEnter)
        }

        return builder.build()
    }

    fun updatePipParams() {
        if (!isPipSupported || !::appEnvironment.isInitialized) return
        try {
            val params = buildPipParams()
            setPictureInPictureParams(params)
        } catch (e: Exception) {
            // Guard against device-specific or vendor bugs
        }
    }

    fun enterPip(): Boolean {
        if (!isPipSupported || !::appEnvironment.isInitialized) return false
        val isPlayerActive = appEnvironment.playerViewModel.activeChannel.value != null ||
            appEnvironment.playerViewModel.activeRecording.value != null
        val isFailed = appEnvironment.playerEngine.state.value is PlaybackState.Failed
        if (!isPlayerActive || appEnvironment.playerEngine.isCasting.value || isFailed) return false
        return try {
            val params = buildPipParams()
            enterPictureInPictureMode(params)
        } catch (e: Exception) {
            false
        }
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        if (::appEnvironment.isInitialized) {
            val isPlayerActive = appEnvironment.playerViewModel.activeChannel.value != null ||
                appEnvironment.playerViewModel.activeRecording.value != null
            val isPlaying = appEnvironment.playerEngine.state.value == PlaybackState.Playing
            val isCasting = appEnvironment.playerEngine.isCasting.value
            if (isPlayerActive && isPlaying && !isCasting && !isInPictureInPictureMode) {
                enterPip()
            }
        }
    }

    override fun onPictureInPictureModeChanged(isInPictureInPictureMode: Boolean, newConfig: Configuration) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        _isInPipMode.value = isInPictureInPictureMode
        if (!isInPictureInPictureMode) {
            updatePipParams()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        runCatching { unregisterReceiver(pipReceiver) }
        ProcessLifecycleOwner.get().lifecycle.removeObserver(processLifecycleObserver)
        if (::appEnvironment.isInitialized) {
            appEnvironment.playerViewModel.closePlayer()
            appEnvironment.playerEngine.release()
        }
    }
}
