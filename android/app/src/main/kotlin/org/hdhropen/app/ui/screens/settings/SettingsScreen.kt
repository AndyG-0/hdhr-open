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
import org.hdhropen.kit.viewmodels.SettingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    settingsViewModel: SettingsViewModel,
    authManager: AuthManager,
    serverDiscovery: ServerDiscovery,
    onUpdateServerURL: (String) -> Unit
) {
    val coroutineScope = rememberCoroutineScope()
    val currentUser by authManager.currentUser.collectAsState()
    val currentServerURL by serverDiscovery.serverURLString.collectAsState()
    val transcodePresets by settingsViewModel.transcodePresets.collectAsState()
    val hwAccelDiagnostics by settingsViewModel.hwAccelDiagnostics.collectAsState()

    var showServerSetupDialog by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        settingsViewModel.loadData()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Settings",
                        style = MaterialTheme.typography.titleLarge.copy(color = TextPrimary, fontWeight = FontWeight.Bold)
                    )
                },
                actions = {
                    IconButton(onClick = { settingsViewModel.loadData() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = TextPrimary)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = DarkSurface)
            )
        },
        containerColor = DarkBackground
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Spacer(modifier = Modifier.height(12.dp))

            // User Profile Section
            Text(text = "PROFILE", style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontWeight = FontWeight.Bold))
            Spacer(modifier = Modifier.height(8.dp))

            Card(
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                modifier = Modifier.fillMaxWidth().border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
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
                                style = MaterialTheme.typography.titleMedium.copy(color = TextPrimary, fontWeight = FontWeight.Bold)
                            )
                            Text(
                                text = "Role: ${currentUser?.role?.name?.lowercase() ?: "member"}",
                                style = MaterialTheme.typography.labelSmall.copy(color = TextSecondary)
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

            // Server Connection Section
            Text(text = "SERVER CONNECTION", style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontWeight = FontWeight.Bold))
            Spacer(modifier = Modifier.height(8.dp))

            Card(
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = DarkSurface),
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .clickable { showServerSetupDialog = true }
                    .border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
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
                                style = MaterialTheme.typography.titleMedium.copy(color = TextPrimary, fontSize = 14.sp)
                            )
                            Text(
                                text = currentServerURL,
                                style = MaterialTheme.typography.labelSmall.copy(color = TextSecondary)
                            )
                        }
                    }
                    Icon(Icons.Default.ChevronRight, contentDescription = "Edit", tint = TextMuted)
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            // Transcoding Presets
            if (transcodePresets.isNotEmpty()) {
                Text(text = "TRANSCODE PRESETS", style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontWeight = FontWeight.Bold))
                Spacer(modifier = Modifier.height(8.dp))

                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    modifier = Modifier.fillMaxWidth().border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
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
                                        style = MaterialTheme.typography.titleMedium.copy(color = TextPrimary, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                                    )
                                    Text(
                                        text = preset.description,
                                        style = MaterialTheme.typography.labelSmall.copy(color = TextSecondary)
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
                Text(text = "HARDWARE ACCELERATION", style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontWeight = FontWeight.Bold))
                Spacer(modifier = Modifier.height(8.dp))

                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = DarkSurface),
                    modifier = Modifier.fillMaxWidth().border(1.dp, DarkBorder, RoundedCornerShape(12.dp))
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = "Device: ${diag.device}",
                            style = MaterialTheme.typography.titleMedium.copy(color = TextPrimary, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        diag.summary.forEach { line ->
                            Text(
                                text = "• $line",
                                style = MaterialTheme.typography.labelSmall.copy(color = TextSecondary)
                            )
                        }
                    }
                }
                Spacer(modifier = Modifier.height(20.dp))
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
