package org.hdhropen.app.ui.screens.player

import android.app.Activity
import android.app.PictureInPictureParams
import android.content.Context
import android.content.ContextWrapper
import android.graphics.Rect
import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.hdhropen.app.PipHelper
import org.hdhropen.app.ui.screens.guide.RecordingOptionsBottomSheet
import org.hdhropen.kit.playback.LoadingQuips
import org.hdhropen.kit.playback.PlaybackState
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.hdhropen.kit.viewmodels.RecordingsViewModel

fun enterPictureInPictureMode(activity: Activity, params: PictureInPictureParams): Boolean {
    return try {
        activity.enterPictureInPictureMode(params)
    } catch (e: Exception) {
        false
    }
}

internal fun Context.findActivity(): Activity? {
    var ctx = this
    while (ctx is ContextWrapper) {
        if (ctx is Activity) return ctx
        ctx = ctx.baseContext
    }
    return null
}

@UnstableApi
@Composable
fun PlayerScreen(
    playerViewModel: PlayerViewModel,
    guideViewModel: GuideViewModel,
    recordingsViewModel: RecordingsViewModel,
    onDismiss: () -> Unit,
    isInPipMode: Boolean = false,
    onEnterPip: (() -> Unit)? = null,
    onUpdateVideoBounds: ((Rect) -> Unit)? = null
) {
    val coroutineScope = rememberCoroutineScope()
    val context = LocalContext.current
    val playerEngine = playerViewModel.playerEngine
    val state by playerEngine.state.collectAsState()
    val currentTime by playerEngine.currentTime.collectAsState()
    val duration by playerEngine.duration.collectAsState()
    val isLive by playerEngine.isLive.collectAsState()
    val isSeekable by playerEngine.isSeekable.collectAsState()
    val availableAudioTracks by playerEngine.availableAudioTracks.collectAsState()
    val currentAudioTrack by playerEngine.currentAudioTrack.collectAsState()
    val videoSpecs by playerEngine.videoSpecs.collectAsState()
    val transcodeInfo by playerEngine.transcodeInfo.collectAsState()
    val observedBitrateBps by playerEngine.observedBitrateBps.collectAsState()
    val playbackMode by playerViewModel.playbackMode.collectAsState()
    val isCasting by playerEngine.isCasting.collectAsState()

    val captionController = playerViewModel.captionController
    val activeCaptionText by captionController.activeCueText.collectAsState()
    val isCaptionsEnabled by captionController.isEnabled.collectAsState()

    val thumbnailCues by playerViewModel.thumbnailCues.collectAsState()
    val isWatchSession by playerViewModel.isWatchSession.collectAsState()
    val isPromoted by playerViewModel.isPromoted.collectAsState()
    val isPromoting by playerViewModel.isPromoting.collectAsState()
    val isSwitchingAudioTrack by playerViewModel.isSwitchingAudioTrack.collectAsState()
    val transientError by playerViewModel.transientError.collectAsState()
    val fallbackNotice by playerViewModel.fallbackNotice.collectAsState()

    val activeChannel by playerViewModel.activeChannel.collectAsState()
    val activeAiring by playerViewModel.activeAiring.collectAsState()
    val channels by guideViewModel.channels.collectAsState()
    val recordingRules by guideViewModel.recordingRules.collectAsState()
    val dvrInfo by recordingsViewModel.dvrInfo.collectAsState()
    val existingRule = remember(recordingRules, activeChannel, activeAiring) {
        guideViewModel.findRule(activeChannel?.channelNumber, activeAiring)
    }

    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(transientError) {
        val err = transientError
        if (err != null) {
            playerViewModel.clearTransientError()
            snackbarHostState.showSnackbar(err)
        }
    }

    LaunchedEffect(fallbackNotice) {
        val notice = fallbackNotice
        if (notice != null) {
            playerViewModel.clearFallbackNotice()
            snackbarHostState.showSnackbar(notice)
        }
    }

    val handleEnterPip: () -> Unit = {
        if (state !is PlaybackState.Failed) {
            if (onEnterPip != null) {
                onEnterPip()
            } else {
                val activity = context.findActivity()
                if (activity != null) {
                    val isPlaying = state == PlaybackState.Playing
                    val exoVideoSize = playerEngine.exoPlayer?.videoSize
                    val width = videoSpecs?.width ?: exoVideoSize?.width
                    val height = videoSpecs?.height ?: exoVideoSize?.height
                    val params = PictureInPictureParams.Builder()
                        .setAspectRatio(PipHelper.calculateAspectRatio(width, height))
                        .setActions(PipHelper.buildRemoteActions(context, isPlaying, isSeekable))
                        .apply {
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                                setAutoEnterEnabled(isPlaying)
                            }
                        }
                        .build()
                    enterPictureInPictureMode(activity, params)
                }
            }
        }
    }

    LaunchedEffect(Unit) {
        if (dvrInfo == null) {
            recordingsViewModel.loadDvrInfo()
        }
    }

    val syncPlayRoom by playerViewModel.syncPlayRoom.collectAsState()
    val syncPlayParticipants by playerViewModel.syncPlayParticipants.collectAsState()

    var showControls by remember { mutableStateOf(true) }
    var showPlaybackInfo by remember { mutableStateOf(false) }
    var showSyncPlaySheet by remember { mutableStateOf(false) }
    var showRecordingOptionsSheet by remember { mutableStateOf(false) }
    var loadingQuip by remember { mutableStateOf(LoadingQuips.getRandomQuip()) }

    // Auto-rotate funny loading quips while loading/buffering
    LaunchedEffect(state) {
        if (state == PlaybackState.Loading || state == PlaybackState.Buffering) {
            loadingQuip = LoadingQuips.getRandomQuip(exclude = loadingQuip)
            while (isActive) {
                delay(2800)
                loadingQuip = LoadingQuips.getRandomQuip(exclude = loadingQuip)
            }
        }
    }

    var isUserScrubbing by remember { mutableStateOf(false) }

    // Auto-hide controls timer (paused while actively scrubbing)
    LaunchedEffect(showControls, state, isUserScrubbing) {
        if (showControls && state == PlaybackState.Playing && !isUserScrubbing) {
            delay(5000)
            showControls = false
        }
    }

    BackHandler(enabled = !isInPipMode) {
        playerViewModel.closePlayer()
        onDismiss()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .then(
                if (!isInPipMode) {
                    Modifier.clickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = null
                    ) {
                        showControls = !showControls
                    }
                } else Modifier
            )
    ) {
        // Video View (Media3 ExoPlayer)
        PlayerSurface(
            player = playerEngine.exoPlayer,
            onUpdateVideoBounds = onUpdateVideoBounds
        )

        // Captions Overlay
        if (!isInPipMode) {
            CaptionsOverlay(
                activeCaptionText = activeCaptionText,
                isCaptionsEnabled = isCaptionsEnabled,
                showControls = showControls,
                modifier = Modifier.align(Alignment.BottomCenter)
            )
        }

        // Loading / Buffering Indicator with Rotating Funny Quips
        if (state == PlaybackState.Loading || state == PlaybackState.Buffering) {
            PlayerLoadingOverlay(
                loadingQuip = loadingQuip,
                modifier = Modifier.align(Alignment.Center)
            )
        }

        // Error Card
        if (state is PlaybackState.Failed) {
            PlayerErrorCard(
                failedState = state as PlaybackState.Failed,
                onRetry = { playerViewModel.retry() },
                onClose = {
                    playerViewModel.closePlayer()
                    onDismiss()
                },
                modifier = Modifier.align(Alignment.Center)
            )
        }

        // Overlay Controls
        AnimatedVisibility(
            visible = showControls && !isInPipMode,
            enter = fadeIn(),
            exit = fadeOut()
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(
                        Brush.verticalGradient(
                            colors = listOf(
                                Color.Black.copy(alpha = 0.7f),
                                Color.Transparent,
                                Color.Black.copy(alpha = 0.85f)
                            )
                        )
                    )
            ) {
                // Top Bar
                PlayerTopBar(
                    title = playerViewModel.mediaTitle,
                    subtitle = playerViewModel.mediaSubtitle,
                    isCasting = isCasting,
                    syncPlayRoom = syncPlayRoom,
                    syncPlayParticipants = syncPlayParticipants,
                    isCaptionsEnabled = isCaptionsEnabled,
                    onToggleCaptions = { captionController.toggleEnabled() },
                    onOpenSyncPlay = { showSyncPlaySheet = true },
                    onOpenPlaybackInfo = { showPlaybackInfo = true },
                    onEnterPip = handleEnterPip,
                    onClose = {
                        playerViewModel.closePlayer()
                        onDismiss()
                    },
                    modifier = Modifier.fillMaxWidth().align(Alignment.TopCenter)
                )

                // Center Play / Skip Controls
                PlayerCenterControls(
                    isPlaying = state == PlaybackState.Playing,
                    isSeekable = isSeekable,
                    onPlayPause = { playerViewModel.togglePlayPause() },
                    onSkipBackward = { playerViewModel.skipBackward(10.0) },
                    onSkipForward = { playerViewModel.skipForward(10.0) },
                    modifier = Modifier.align(Alignment.Center)
                )

                // Bottom Timeline & Actions
                PlayerBottomBar(
                    currentTime = currentTime,
                    duration = duration,
                    isLive = isLive,
                    isSeekable = isSeekable,
                    thumbnailCues = thumbnailCues,
                    isWatchSession = isWatchSession,
                    isPromoted = isPromoted,
                    isPromoting = isPromoting,
                    existingRule = existingRule,
                    activeAiring = activeAiring,
                    availableAudioTracks = availableAudioTracks,
                    currentAudioTrack = currentAudioTrack,
                    isSwitchingAudioTrack = isSwitchingAudioTrack,
                    onSeek = { target -> playerViewModel.seek(target) },
                    onScrubbingStateChange = { isUserScrubbing = it },
                    onPromoteToRecording = { playerViewModel.promoteToRecording() },
                    onRecordEpisode = {
                        coroutineScope.launch {
                            guideViewModel.recordEpisode(
                                seriesId = activeAiring?.seriesId,
                                channelNumber = activeChannel?.channelNumber,
                                start = activeAiring?.start
                            )
                        }
                    },
                    onRecordSeries = {
                        coroutineScope.launch {
                            guideViewModel.recordSeries(
                                seriesId = activeAiring?.seriesId ?: "",
                                channelNumber = activeChannel?.channelNumber
                            )
                        }
                    },
                    onCancelRule = { ruleId ->
                        coroutineScope.launch { guideViewModel.cancelRule(ruleId) }
                    },
                    onOpenRecordingOptions = { showRecordingOptionsSheet = true },
                    onSelectAudioTrack = { track -> playerViewModel.selectAudioTrack(track) },
                    modifier = Modifier.fillMaxWidth().align(Alignment.BottomCenter)
                )
            }
        }

        SnackbarHost(
            hostState = snackbarHostState,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = if (showControls && !isInPipMode) 90.dp else 16.dp)
        )

        if (!isInPipMode && showPlaybackInfo) {
            PlaybackInfoDialog(
                playbackMode = playbackMode,
                transcodeInfo = transcodeInfo,
                videoSpecs = videoSpecs,
                audioTracks = availableAudioTracks,
                observedBitrateBps = observedBitrateBps,
                onDismiss = { showPlaybackInfo = false }
            )
        }

        if (!isInPipMode && showRecordingOptionsSheet && activeChannel != null && activeAiring != null) {
            RecordingOptionsBottomSheet(
                channel = activeChannel!!,
                airing = activeAiring!!,
                channels = channels,
                canRecordSeries = !activeAiring!!.seriesId.isNullOrEmpty() || activeAiring!!.title.isNotEmpty(),
                officialDvrActive = dvrInfo?.isBuiltin == false,
                existingRule = existingRule,
                onConfirm = { isSeries, options ->
                    coroutineScope.launch {
                        if (existingRule != null) {
                            guideViewModel.updateRule(
                                ruleId = existingRule.recordingRuleId,
                                isSeries = isSeries,
                                options = options,
                                seriesId = activeAiring?.seriesId,
                                start = activeAiring?.start,
                                channelNumber = activeChannel?.channelNumber
                            )
                        } else if (isSeries) {
                            guideViewModel.recordSeries(
                                seriesId = activeAiring?.seriesId ?: "",
                                channelNumber = activeChannel?.channelNumber,
                                options = options
                            )
                        } else {
                            guideViewModel.recordEpisode(
                                seriesId = activeAiring?.seriesId,
                                channelNumber = activeChannel?.channelNumber,
                                start = activeAiring?.start,
                                options = options
                            )
                        }
                    }
                },
                onCancelRule = existingRule?.let { rule ->
                    { coroutineScope.launch { guideViewModel.cancelRule(rule.recordingRuleId) } }
                },
                onDismiss = { showRecordingOptionsSheet = false }
            )
        }

        if (!isInPipMode && showSyncPlaySheet) {
            SyncPlayBottomSheet(
                playerViewModel = playerViewModel,
                onDismiss = { showSyncPlaySheet = false }
            )
        }
    }
}
