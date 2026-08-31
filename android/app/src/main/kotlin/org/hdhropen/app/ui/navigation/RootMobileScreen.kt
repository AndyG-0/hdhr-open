package org.hdhropen.app.ui.navigation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.screens.auth.ProfilePickerScreen
import org.hdhropen.app.ui.screens.guide.GuideScreen
import org.hdhropen.app.ui.screens.player.PlayerScreen
import org.hdhropen.app.ui.screens.recordings.RecordingsScreen
import org.hdhropen.app.ui.screens.settings.SettingsScreen
import org.hdhropen.app.ui.screens.tuners.TunerStatusScreen
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.viewmodels.AppEnvironment

@UnstableApi
@Composable
fun RootMobileScreen(appEnvironment: AppEnvironment) {
    val coroutineScope = rememberCoroutineScope()
    val authManager = appEnvironment.authManager
    val currentUser by authManager.currentUser.collectAsState()
    val playerViewModel = appEnvironment.playerViewModel
    val activeChannel by playerViewModel.activeChannel.collectAsState()
    val activeRecording by playerViewModel.activeRecording.collectAsState()

    var selectedTab by remember { mutableStateOf(AppTab.GUIDE) }

    val isPlayerActive = activeChannel != null || activeRecording != null

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
                        AppTab.values().forEach { tab ->
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
                            playerViewModel = playerViewModel
                        )
                        AppTab.RECORDINGS -> RecordingsScreen(
                            recordingsViewModel = appEnvironment.recordingsViewModel,
                            playerViewModel = playerViewModel
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
                onDismiss = { playerViewModel.closePlayer() }
            )
        }
    }
}
