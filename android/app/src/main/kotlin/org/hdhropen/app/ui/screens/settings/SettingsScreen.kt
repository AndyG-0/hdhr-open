package org.hdhropen.app.ui.screens.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.networking.AuthManager
import org.hdhropen.kit.networking.ServerDiscovery
import org.hdhropen.kit.playback.PlaybackPreferences
import org.hdhropen.kit.playback.QualityPreference
import org.hdhropen.kit.theme.ThemeMode
import org.hdhropen.kit.theme.ThemePreferences
import org.hdhropen.kit.viewmodels.SettingsViewModel

private enum class SettingsGroup(val label: String) {
    GENERAL("General"),
    SERVER_AND_ADVANCED("Server & Advanced"),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    settingsViewModel: SettingsViewModel,
    authManager: AuthManager,
    serverDiscovery: ServerDiscovery,
    playbackPreferences: PlaybackPreferences,
    themePreferences: ThemePreferences,
    onUpdateServerURL: (String) -> Unit
) {
    val coroutineScope = rememberCoroutineScope()
    val currentUser by authManager.currentUser.collectAsStateWithLifecycle()
    val currentServerURL by serverDiscovery.serverURLString.collectAsStateWithLifecycle()
    val transcodePresets by settingsViewModel.transcodePresets.collectAsStateWithLifecycle()
    val hwAccelDiagnostics by settingsViewModel.hwAccelDiagnostics.collectAsStateWithLifecycle()
    val directPlayEnabled by playbackPreferences.directPlayEnabled.collectAsStateWithLifecycle()
    val autoSkipCommercialsEnabled by playbackPreferences.autoSkipCommercialsEnabled.collectAsStateWithLifecycle()
    val qualityPreference by playbackPreferences.qualityPreference.collectAsStateWithLifecycle()
    val themeMode by themePreferences.themeMode.collectAsStateWithLifecycle()

    var showServerSetupDialog by remember { mutableStateOf(false) }
    var selectedGroup by remember { mutableStateOf(SettingsGroup.GENERAL) }

    LaunchedEffect(Unit) {
        settingsViewModel.loadData()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Settings",
                        style = MaterialTheme.typography.titleLarge.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
                    )
                },
                actions = {
                    IconButton(onClick = { settingsViewModel.loadData() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = MaterialTheme.colorScheme.onSurface)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
            )
        },
        containerColor = MaterialTheme.colorScheme.background
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            TabRow(selectedTabIndex = selectedGroup.ordinal) {
                SettingsGroup.values().forEach { group ->
                    Tab(
                        selected = selectedGroup == group,
                        onClick = { selectedGroup = group },
                        text = { Text(group.label) }
                    )
                }
            }

            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Spacer(modifier = Modifier.height(12.dp))

                if (selectedGroup == SettingsGroup.GENERAL) {
                    // Appearance Section
                    Text(text = "APPEARANCE", style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted, fontWeight = FontWeight.Bold))
                    Spacer(modifier = Modifier.height(8.dp))

                    Card(
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        modifier = Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text(
                                text = "Theme",
                                style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                            )
                            Spacer(modifier = Modifier.height(10.dp))
                            SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
                                val options = listOf(
                                    ThemeMode.SYSTEM to "System",
                                    ThemeMode.LIGHT to "Light",
                                    ThemeMode.DARK to "Dark"
                                )
                                options.forEachIndexed { index, (mode, label) ->
                                    SegmentedButton(
                                        selected = themeMode == mode,
                                        onClick = { themePreferences.setThemeMode(mode) },
                                        shape = SegmentedButtonDefaults.itemShape(index = index, count = options.size)
                                    ) {
                                        Text(label)
                                    }
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    // User Profile Section
                    Text(text = "PROFILE", style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted, fontWeight = FontWeight.Bold))
                    Spacer(modifier = Modifier.height(8.dp))

                    Card(
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        modifier = Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp).fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Person, contentDescription = "User", tint = BluePrimary)
                                Spacer(modifier = Modifier.width(12.dp))
                                Column {
                                    Text(
                                        text = currentUser?.name ?: "Unknown User",
                                        style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
                                    )
                                    Text(
                                        text = "Role: ${currentUser?.role?.name?.lowercase() ?: "member"}",
                                        style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    )
                                }
                            }

                            OutlinedButton(
                                onClick = {
                                    coroutineScope.launch { authManager.logout() }
                                },
                                colors = ButtonDefaults.outlinedButtonColors(contentColor = RedLive),
                                shape = RoundedCornerShape(8.dp)
                            ) {
                                Icon(Icons.Default.ExitToApp, contentDescription = "Logout", tint = RedLive, modifier = Modifier.size(16.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Logout", color = RedLive, style = MaterialTheme.typography.labelMedium)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    // Playback
                    Text(text = "PLAYBACK", style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted, fontWeight = FontWeight.Bold))
                    Spacer(modifier = Modifier.height(8.dp))

                    Card(
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        modifier = Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = "Direct Play",
                                        style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                                    )
                                    Text(
                                        text = "Play live channels without server-side transcoding. Faster and lighter on the server, but live pause/rewind and tuner sharing with other viewers are unavailable while it's on.",
                                        style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    )
                                }
                                Switch(
                                    checked = directPlayEnabled,
                                    onCheckedChange = { playbackPreferences.setDirectPlayEnabled(it) }
                                )
                            }

                            Spacer(modifier = Modifier.height(16.dp))

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = "Auto-skip Commercials",
                                        style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                                    )
                                    Text(
                                        text = "Automatically skip past detected commercial breaks during playback, without needing to tap Skip Commercial.",
                                        style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    )
                                }
                                Switch(
                                    checked = autoSkipCommercialsEnabled,
                                    onCheckedChange = { playbackPreferences.setAutoSkipCommercialsEnabled(it) }
                                )
                            }

                            Spacer(modifier = Modifier.height(16.dp))

                            Text(
                                text = "Video Quality",
                                style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                            )
                            Text(
                                text = "Default quality for new playback sessions. Auto adjusts to network conditions automatically.",
                                style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                            )
                            Spacer(modifier = Modifier.height(10.dp))
                            SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
                                val qualityOptions = listOf(
                                    QualityPreference.AUTO to "Auto",
                                    QualityPreference.HIGH to "High",
                                    QualityPreference.MEDIUM to "Medium",
                                    QualityPreference.LOW to "Low"
                                )
                                qualityOptions.forEachIndexed { index, (preference, label) ->
                                    SegmentedButton(
                                        selected = qualityPreference == preference,
                                        onClick = { playbackPreferences.setQualityPreference(preference) },
                                        shape = SegmentedButtonDefaults.itemShape(index = index, count = qualityOptions.size)
                                    ) {
                                        Text(label)
                                    }
                                }
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(20.dp))
                }

                if (selectedGroup == SettingsGroup.SERVER_AND_ADVANCED) {
                    // Server Connection Section
                    Text(text = "SERVER CONNECTION", style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted, fontWeight = FontWeight.Bold))
                    Spacer(modifier = Modifier.height(8.dp))

                    Card(
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(12.dp))
                            .clickable { showServerSetupDialog = true }
                            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
                    ) {
                        Row(
                            modifier = Modifier.padding(16.dp).fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Dns, contentDescription = "Server", tint = YellowAccent)
                                Spacer(modifier = Modifier.width(12.dp))
                                Column {
                                    Text(
                                        text = "Server Address",
                                        style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp)
                                    )
                                    Text(
                                        text = currentServerURL,
                                        style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    )
                                }
                            }
                            Icon(Icons.Default.ChevronRight, contentDescription = "Edit", tint = MaterialTheme.extendedColors.textMuted)
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    // Transcoding Presets
                    if (transcodePresets.isNotEmpty()) {
                        Text(text = "TRANSCODE PRESETS", style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted, fontWeight = FontWeight.Bold))
                        Spacer(modifier = Modifier.height(8.dp))

                        Card(
                            shape = RoundedCornerShape(12.dp),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                            modifier = Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
                        ) {
                            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                                transcodePresets.forEach { preset ->
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = preset.label,
                                                style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                                            )
                                            Text(
                                                text = preset.description,
                                                style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                                            )
                                        }
                                        if (preset.hardware) {
                                            Box(
                                                modifier = Modifier
                                                    .clip(RoundedCornerShape(4.dp))
                                                    .background(GreenActive.copy(alpha = 0.2f))
                                                    .padding(horizontal = 6.dp, vertical = 2.dp)
                                            ) {
                                                Text(
                                                    text = "HW",
                                                    style = MaterialTheme.typography.labelSmall.copy(color = GreenActive, fontWeight = FontWeight.Bold)
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(20.dp))
                    }

                    // Hardware Acceleration Diagnostics
                    hwAccelDiagnostics?.let { diag ->
                        Text(text = "HARDWARE ACCELERATION", style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted, fontWeight = FontWeight.Bold))
                        Spacer(modifier = Modifier.height(8.dp))

                        Card(
                            shape = RoundedCornerShape(12.dp),
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                            modifier = Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text(
                                    text = "Device: ${diag.device}",
                                    style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                                )
                                Spacer(modifier = Modifier.height(6.dp))
                                diag.summary.forEach { line ->
                                    Text(
                                        text = "• $line",
                                        style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    )
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(20.dp))
                    }
                }
            }
        }

        if (showServerSetupDialog) {
            ServerSetupDialog(
                serverDiscovery = serverDiscovery,
                onDismiss = { showServerSetupDialog = false },
                onSaveURL = { newURL ->
                    onUpdateServerURL(newURL)
                }
            )
        }
    }
}
