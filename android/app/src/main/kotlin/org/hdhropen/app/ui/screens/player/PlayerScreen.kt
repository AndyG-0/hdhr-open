package org.hdhropen.app.ui.screens.player
 
import android.app.Activity
import android.app.PictureInPictureParams
import android.content.Context
import android.content.ContextWrapper
import android.graphics.Rect
import android.os.Build
import android.view.ViewGroup
import android.widget.FrameLayout
import androidx.activity.compose.BackHandler
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.mediarouter.app.MediaRouteButton
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.PlayerView
import com.google.android.gms.cast.framework.CastButtonFactory
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.hdhropen.app.PipHelper
import org.hdhropen.app.ui.screens.guide.RecordingOptionsBottomSheet
import org.hdhropen.app.ui.theme.*
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

    val activeChannel by playerViewModel.activeChannel.collectAsState()
    val activeAiring by playerViewModel.activeAiring.collectAsState()
    val channels by guideViewModel.channels.collectAsState()
    val recordingRules by guideViewModel.recordingRules.collectAsState()
    val dvrInfo by recordingsViewModel.dvrInfo.collectAsState()
    val existingRule = remember(recordingRules, activeChannel, activeAiring) {
        guideViewModel.findRule(activeChannel?.channelNumber, activeAiring)
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
    var showAudioMenu by remember { mutableStateOf(false) }
    var showPlaybackInfo by remember { mutableStateOf(false) }
    var showSyncPlaySheet by remember { mutableStateOf(false) }
    var showRecordMenu by remember { mutableStateOf(false) }
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
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    useController = false
                    layoutParams = FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        ViewGroup.LayoutParams.MATCH_PARENT
                    )
                    player = playerEngine.exoPlayer
                }
            },
            update = { view ->
                view.player = playerEngine.exoPlayer
            },
            modifier = Modifier
                .fillMaxSize()
                .onGloballyPositioned { coordinates ->
                    val bounds = coordinates.boundsInWindow()
                    onUpdateVideoBounds?.invoke(
                        Rect(
                            bounds.left.toInt(),
                            bounds.top.toInt(),
                            bounds.right.toInt(),
                            bounds.bottom.toInt()
                        )
                    )
                }
        )

        // Captions Overlay
        if (!isInPipMode && isCaptionsEnabled && !activeCaptionText.isNullOrEmpty()) {
            Box(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = if (showControls) 120.dp else 40.dp)
                    .padding(horizontal = 24.dp)
                    .clip(RoundedCornerShape(6.dp))
                    .background(Color.Black.copy(alpha = 0.75f))
                    .padding(horizontal = 12.dp, vertical = 6.dp)
            ) {
                Text(
                    text = activeCaptionText ?: "",
                    style = MaterialTheme.typography.bodyMedium.copy(
                        color = YellowAccent,
                        fontWeight = FontWeight.Bold,
                        textAlign = TextAlign.Center
                    )
                )
            }
        }

        // Loading / Buffering Indicator with Rotating Funny Quips
        if (state == PlaybackState.Loading || state == PlaybackState.Buffering) {
            Column(
                modifier = Modifier
                    .align(Alignment.Center)
                    .padding(32.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                CircularProgressIndicator(
                    color = BluePrimary,
                    modifier = Modifier.size(56.dp),
                    strokeWidth = 4.dp
                )
                Spacer(modifier = Modifier.height(20.dp))
                AnimatedContent(
                    targetState = loadingQuip,
                    transitionSpec = {
                        fadeIn() togetherWith fadeOut()
                    },
                    label = "loadingQuipAnimation"
                ) { quip ->
                    Text(
                        text = quip,
                        style = MaterialTheme.typography.bodyLarge.copy(
                            color = Color.White,
                            fontWeight = FontWeight.Medium,
                            textAlign = TextAlign.Center
                        ),
                        modifier = Modifier.padding(horizontal = 24.dp)
                    )
                }
            }
        }

        // Error Card
        if (state is PlaybackState.Failed) {
            val failedState = state as PlaybackState.Failed
            Card(
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface.copy(alpha = 0.95f)),
                modifier = Modifier
                    .align(Alignment.Center)
                    .padding(32.dp)
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(
                        if (failedState.statusCode in 500..599 || failedState.isNetworkError) Icons.Default.CloudOff else Icons.Default.Warning,
                        contentDescription = "Error",
                        tint = YellowAccent,
                        modifier = Modifier.size(48.dp)
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = if (failedState.statusCode in 500..599 || failedState.isNetworkError) "Server / Tuner Unavailable" else "Playback Error",
                        style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = failedState.message,
                        style = MaterialTheme.typography.bodyMedium.copy(color = MaterialTheme.colorScheme.onSurface, textAlign = TextAlign.Center)
                    )
                    val detail = failedState.detail
                    if (!detail.isNullOrBlank() && detail != failedState.message) {
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            text = detail,
                            style = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
                        )
                    }
                    Spacer(modifier = Modifier.height(20.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        OutlinedButton(
                            onClick = {
                                playerViewModel.closePlayer()
                                onDismiss()
                            }
                        ) {
                            Text("Close")
                        }
                        Button(
                            onClick = {
                                playerViewModel.retry()
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = BluePrimary)
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("Retry", color = Color.White)
                        }
                    }
                }
            }
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
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .align(Alignment.TopCenter)
                        .statusBarsPadding()
                        .padding(horizontal = 16.dp, vertical = 20.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    IconButton(onClick = {
                        playerViewModel.closePlayer()
                        onDismiss()
                    }) {
                        Icon(
                            Icons.Default.KeyboardArrowDown,
                            contentDescription = "Close",
                            tint = Color.White,
                            modifier = Modifier.size(36.dp)
                        )
                    }

                    Column(
                        modifier = Modifier.weight(1f).padding(horizontal = 8.dp),
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = playerViewModel.mediaTitle,
                            style = MaterialTheme.typography.titleMedium.copy(
                                color = Color.White,
                                fontWeight = FontWeight.Bold
                            ),
                            maxLines = 1
                        )
                        if (isCasting) {
                            Text(
                                text = "Casting to TV",
                                style = MaterialTheme.typography.bodySmall.copy(color = YellowAccent),
                                maxLines = 1
                            )
                        } else {
                            playerViewModel.mediaSubtitle?.let { sub ->
                                Text(
                                    text = sub,
                                    style = MaterialTheme.typography.bodySmall.copy(color = Color.White.copy(alpha = 0.8f)),
                                    maxLines = 1
                                )
                            }
                        }
                    }

                    // Cast Button - self-manages its route icon/state once wired
                    // to the shared CastContext, so `update` has nothing to sync.
                    AndroidView(
                        factory = { ctx ->
                            try {
                                val themedContext = android.view.ContextThemeWrapper(
                                    ctx,
                                    androidx.appcompat.R.style.Theme_AppCompat_NoActionBar
                                )
                                MediaRouteButton(themedContext).apply {
                                    runCatching { CastButtonFactory.setUpMediaRouteButton(themedContext, this) }
                                }
                            } catch (e: Throwable) {
                                android.view.View(ctx)
                            }
                        },
                        modifier = Modifier.size(48.dp)
                    )

                    // SyncPlay Watch Party Toggle
                    IconButton(onClick = { showSyncPlaySheet = true }) {
                        BadgedBox(
                            badge = {
                                if (syncPlayRoom != null && syncPlayParticipants.isNotEmpty()) {
                                    Badge(containerColor = BluePrimary) {
                                        Text(syncPlayParticipants.size.toString())
                                    }
                                }
                            }
                        ) {
                            Icon(
                                Icons.Default.Group,
                                contentDescription = "SyncPlay Watch Party",
                                tint = if (syncPlayRoom != null) BluePrimary else Color.White
                            )
                        }
                    }

                    // Playback Info Toggle
                    IconButton(onClick = { showPlaybackInfo = true }) {
                        Icon(
                            Icons.Default.Info,
                            contentDescription = "Playback Info",
                            tint = Color.White
                        )
                    }

                    // Captions Toggle
                    IconButton(onClick = { captionController.toggleEnabled() }) {
                        Icon(
                            Icons.Default.ClosedCaption,
                            contentDescription = "Captions",
                            tint = if (isCaptionsEnabled) YellowAccent else Color.White
                        )
                    }

                    // Picture-in-Picture Toggle (suppressed when casting to remote TV)
                    if (!isCasting) {
                        IconButton(onClick = handleEnterPip) {
                            Icon(
                                Icons.Default.PictureInPictureAlt,
                                contentDescription = "Picture-in-Picture",
                                tint = Color.White
                            )
                        }
                    }
                }

                // Center Play / Skip Controls
                Row(
                    modifier = Modifier.align(Alignment.Center),
                    horizontalArrangement = Arrangement.spacedBy(40.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (isSeekable) {
                        IconButton(
                            onClick = { playerViewModel.skipBackward(10.0) },
                            modifier = Modifier.size(52.dp)
                        ) {
                            Icon(
                                Icons.Default.Replay10,
                                contentDescription = "Skip Back 10s",
                                tint = Color.White,
                                modifier = Modifier.size(36.dp)
                            )
                        }
                    }

                    IconButton(
                        onClick = { playerViewModel.togglePlayPause() },
                        modifier = Modifier.size(72.dp)
                    ) {
                        Icon(
                            if (state == PlaybackState.Playing) Icons.Default.PauseCircle else Icons.Default.PlayCircle,
                            contentDescription = "Play/Pause",
                            tint = Color.White,
                            modifier = Modifier.size(68.dp)
                        )
                    }

                    if (isSeekable) {
                        IconButton(
                            onClick = { playerViewModel.skipForward(10.0) },
                            modifier = Modifier.size(52.dp)
                        ) {
                            Icon(
                                Icons.Default.Forward10,
                                contentDescription = "Skip Forward 10s",
                                tint = Color.White,
                                modifier = Modifier.size(36.dp)
                            )
                        }
                    }
                }

                // Bottom Timeline & Actions
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .align(Alignment.BottomCenter)
                        .navigationBarsPadding()
                        .padding(horizontal = 20.dp, vertical = 20.dp)
                ) {
                    ScrubBar(
                        currentTime = currentTime,
                        duration = duration,
                        isLive = isLive,
                        isSeekable = isSeekable,
                        thumbnailCues = thumbnailCues,
                        onSeek = { target -> playerViewModel.seek(target) },
                        onScrubbingStateChange = { isUserScrubbing = it }
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        // Record Live Button + Menu (mirrors HDHomeRunPlayerRecordMenu.svelte:
                        // a scheduled rule for the current airing/channel shows only "Cancel
                        // Recording"; otherwise the menu offers episode/series rules, options,
                        // and this app's own quick "save the buffering watch session" action).
                        if (isWatchSession) {
                            Box {
                                Button(
                                    onClick = { showRecordMenu = !showRecordMenu },
                                    colors = ButtonDefaults.buttonColors(containerColor = Color.White.copy(alpha = 0.2f)),
                                    shape = RoundedCornerShape(8.dp),
                                    enabled = !isPromoting
                                ) {
                                    Icon(
                                        if (existingRule != null || isPromoted) Icons.Default.CheckCircle else Icons.Default.FiberManualRecord,
                                        contentDescription = "Record",
                                        tint = if (existingRule != null || isPromoted) GreenActive else RedLive,
                                        modifier = Modifier.size(16.dp)
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = when {
                                            existingRule != null -> "Recording Scheduled"
                                            isPromoted -> "Recording Saved"
                                            else -> "Record"
                                        },
                                        style = MaterialTheme.typography.labelMedium.copy(color = Color.White, fontWeight = FontWeight.Bold)
                                    )
                                }

                                DropdownMenu(
                                    expanded = showRecordMenu,
                                    onDismissRequest = { showRecordMenu = false },
                                    modifier = Modifier.background(MaterialTheme.colorScheme.surface)
                                ) {
                                    if (existingRule != null) {
                                        DropdownMenuItem(
                                            text = { Text("Cancel Recording", color = RedLive) },
                                            onClick = {
                                                showRecordMenu = false
                                                coroutineScope.launch { guideViewModel.cancelRule(existingRule.recordingRuleId) }
                                            }
                                        )
                                        DropdownMenuItem(
                                            text = { Text("Recording Options…") },
                                            onClick = {
                                                showRecordMenu = false
                                                showRecordingOptionsSheet = true
                                            }
                                        )
                                    } else {
                                        DropdownMenuItem(
                                            text = { Text(if (isPromoted) "Recording Saved" else "Save Current Recording") },
                                            enabled = !isPromoted && !isPromoting,
                                            onClick = {
                                                showRecordMenu = false
                                                playerViewModel.promoteToRecording()
                                            }
                                        )
                                        DropdownMenuItem(
                                            text = { Text("Record Episode") },
                                            onClick = {
                                                showRecordMenu = false
                                                coroutineScope.launch {
                                                    guideViewModel.recordEpisode(
                                                        seriesId = activeAiring?.seriesId,
                                                        channelNumber = activeChannel?.channelNumber,
                                                        start = activeAiring?.start
                                                    )
                                                }
                                            }
                                        )
                                        if (!activeAiring?.seriesId.isNullOrEmpty() || !activeAiring?.title.isNullOrEmpty()) {
                                            DropdownMenuItem(
                                                text = { Text("Record Series") },
                                                onClick = {
                                                    showRecordMenu = false
                                                    coroutineScope.launch {
                                                        guideViewModel.recordSeries(
                                                            seriesId = activeAiring?.seriesId ?: "",
                                                            channelNumber = activeChannel?.channelNumber
                                                        )
                                                    }
                                                }
                                            )
                                        }
                                        DropdownMenuItem(
                                            text = { Text("Recording Options…") },
                                            onClick = {
                                                showRecordMenu = false
                                                showRecordingOptionsSheet = true
                                            }
                                        )
                                    }
                                }
                            }
                        } else {
                            Spacer(modifier = Modifier.width(1.dp))
                        }

                        // Audio Track Selector
                        if (availableAudioTracks.isNotEmpty()) {
                            Box {
                                IconButton(onClick = { showAudioMenu = !showAudioMenu }) {
                                    Icon(
                                        Icons.Default.GraphicEq,
                                        contentDescription = "Audio Tracks",
                                        tint = Color.White
                                    )
                                }

                                DropdownMenu(
                                    expanded = showAudioMenu,
                                    onDismissRequest = { showAudioMenu = false },
                                    modifier = Modifier.background(MaterialTheme.colorScheme.surface)
                                ) {
                                    availableAudioTracks.forEach { track ->
                                        DropdownMenuItem(
                                            text = {
                                                Text(
                                                    text = track.displayLabel,
                                                    color = if (track.index == currentAudioTrack?.index) BluePrimary else MaterialTheme.colorScheme.onSurface
                                                )
                                            },
                                            enabled = !isSwitchingAudioTrack,
                                            onClick = {
                                                playerViewModel.selectAudioTrack(track)
                                                showAudioMenu = false
                                            }
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

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
