package org.hdhropen.app.ui.navigation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.Modifier
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.screens.auth.ProfilePickerScreen
import org.hdhropen.app.ui.screens.discovery.DiscoveryScreen
import org.hdhropen.app.ui.screens.guide.GuideScreen
import org.hdhropen.app.ui.screens.player.PlayerScreen
import org.hdhropen.app.ui.screens.recordings.RecordingsScreen
import org.hdhropen.app.ui.screens.settings.SettingsScreen
import org.hdhropen.app.ui.screens.tuners.TunerStatusScreen
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.viewmodels.AppEnvironment

@UnstableApi
@Composable
fun RootMobileScreen(
    appEnvironment: AppEnvironment,
    isInPipMode: Boolean = false,
    onEnterPip: (() -> Unit)? = null,
    onUpdateVideoBounds: ((android.graphics.Rect) -> Unit)? = null
) {
    val coroutineScope = rememberCoroutineScope()
    val authManager = appEnvironment.authManager
    val currentUser by authManager.currentUser.collectAsStateWithLifecycle()
    val playerViewModel = appEnvironment.playerViewModel
    val activeChannel by playerViewModel.activeChannel.collectAsStateWithLifecycle()
    val activeRecording by playerViewModel.activeRecording.collectAsStateWithLifecycle()
    val discoveryViewModel = appEnvironment.discoveryViewModel
    val discoveryEnabled by discoveryViewModel.enabled.collectAsStateWithLifecycle()

    var selectedTab by remember { mutableStateOf(AppTab.GUIDE) }

    val isPlayerActive = activeChannel != null || activeRecording != null

    // The Discovery tab's visibility comes from GET /api/discovery's `enabled`
    // field (the admin's web-only Settings toggle), not a settings flag read
    // locally - so it needs loading as soon as there's a signed-in user,
    // independent of whether the Discovery tab is ever selected.
    LaunchedEffect(currentUser) {
        if (currentUser != null) {
            discoveryViewModel.loadData()
        }
    }

    // If Discovery becomes unavailable while selected (e.g. the flag flips
    // off after a refresh), fall back to a tab that's always shown.
    LaunchedEffect(discoveryEnabled) {
        if (!discoveryEnabled && selectedTab == AppTab.DISCOVERY) {
            selectedTab = AppTab.GUIDE
        }
    }

    Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        if (currentUser == null) {
            ProfilePickerScreen(
                authManager = authManager,
                authViewModel = appEnvironment.authViewModel,
                serverDiscovery = appEnvironment.serverDiscovery,
                onUpdateServerURL = { url ->
                    appEnvironment.updateServerURL(url)
                    coroutineScope.launch {
                        authManager.fetchProfiles()
                    }
                }
            )
        } else {
            Scaffold(
                bottomBar = {
                    NavigationBar(
                        containerColor = MaterialTheme.colorScheme.surface,
                        contentColor = MaterialTheme.colorScheme.onSurface
                    ) {
                        AppTab.values().filter { it != AppTab.DISCOVERY || discoveryEnabled }.forEach { tab ->
                            NavigationBarItem(
                                selected = selectedTab == tab,
                                onClick = { selectedTab = tab },
                                icon = {
                                    Icon(
                                        tab.icon,
                                        contentDescription = tab.title,
                                        tint = if (selectedTab == tab) BluePrimary else MaterialTheme.extendedColors.textMuted
                                    )
                                },
                                label = {
                                    Text(
                                        tab.title,
                                        style = MaterialTheme.typography.labelSmall.copy(
                                            color = if (selectedTab == tab) BluePrimary else MaterialTheme.extendedColors.textMuted
                                        )
                                    )
                                },
                                colors = NavigationBarItemDefaults.colors(
                                    selectedIconColor = BluePrimary,
                                    indicatorColor = MaterialTheme.colorScheme.surfaceVariant
                                )
                            )
                        }
                    }
                },
                containerColor = MaterialTheme.colorScheme.background
            ) { innerPadding ->
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(innerPadding)
                ) {
                    when (selectedTab) {
                        AppTab.GUIDE -> GuideScreen(
                            guideViewModel = appEnvironment.guideViewModel,
                            recordingsViewModel = appEnvironment.recordingsViewModel,
                            playerViewModel = playerViewModel
                        )
                        AppTab.RECORDINGS -> RecordingsScreen(
                            recordingsViewModel = appEnvironment.recordingsViewModel,
                            guideViewModel = appEnvironment.guideViewModel,
                            playerViewModel = playerViewModel
                        )
                        AppTab.DISCOVERY -> DiscoveryScreen(
                            discoveryViewModel = discoveryViewModel,
                            guideViewModel = appEnvironment.guideViewModel,
                            recordingsViewModel = appEnvironment.recordingsViewModel
                        )
                        AppTab.TUNERS -> TunerStatusScreen(
                            tunerViewModel = appEnvironment.tunerViewModel
                        )
                        AppTab.SETTINGS -> SettingsScreen(
                            settingsViewModel = appEnvironment.settingsViewModel,
                            authManager = authManager,
                            serverDiscovery = appEnvironment.serverDiscovery,
                            playbackPreferences = appEnvironment.playbackPreferences,
                            themePreferences = appEnvironment.themePreferences,
                            onUpdateServerURL = { url -> appEnvironment.updateServerURL(url) }
                        )
                    }
                }
            }
        }

        // Fullscreen overlay for Video Player
        if (isPlayerActive) {
            PlayerScreen(
                playerViewModel = playerViewModel,
                guideViewModel = appEnvironment.guideViewModel,
                recordingsViewModel = appEnvironment.recordingsViewModel,
                onDismiss = { playerViewModel.closePlayer() },
                isInPipMode = isInPipMode,
                onEnterPip = onEnterPip,
                onUpdateVideoBounds = onUpdateVideoBounds
            )
        }
    }
}
