package org.hdhropen.app.ui.screens.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.networking.ServerDiscovery

@Composable
fun ServerSetupDialog(
    serverDiscovery: ServerDiscovery,
    onDismiss: () -> Unit,
    onSaveURL: (String) -> Unit
) {
    val coroutineScope = rememberCoroutineScope()
    val currentURL by serverDiscovery.serverURLString.collectAsState()
    val discoveredServers by serverDiscovery.discoveredServers.collectAsState()
    val isSearching by serverDiscovery.isSearching.collectAsState()

    var inputURL by remember { mutableStateOf(currentURL) }
    var testResult by remember { mutableStateOf<Boolean?>(null) }
    var isTesting by remember { mutableStateOf(false) }

    DisposableEffect(Unit) {
        serverDiscovery.startDiscovery()
        onDispose {
            serverDiscovery.stopDiscovery()
        }
    }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = DarkSurface,
            modifier = Modifier.fillMaxWidth().fillMaxHeight(0.8f).padding(16.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Server Setup",
                        style = MaterialTheme.typography.titleMedium.copy(color = TextPrimary, fontWeight = FontWeight.Bold)
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = TextSecondary)
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Manual URL Input
                OutlinedTextField(
                    value = inputURL,
                    onValueChange = {
                        inputURL = it
                        testResult = null
                    },
                    label = { Text("Server URL", color = TextSecondary) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedContainerColor = DarkSurfaceVariant,
                        unfocusedContainerColor = DarkSurfaceVariant,
                        focusedBorderColor = BluePrimary,
                        unfocusedBorderColor = DarkBorder,
                        focusedTextColor = TextPrimary,
                        unfocusedTextColor = TextPrimary
                    )
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Test Connection & Save
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Button(
                        onClick = {
                            coroutineScope.launch {
                                isTesting = true
                                testResult = serverDiscovery.testConnection(inputURL)
                                isTesting = false
                            }
                        },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = DarkSurfaceVariant),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        if (isTesting) {
                            CircularProgressIndicator(color = BluePrimary, modifier = Modifier.size(16.dp))
                        } else {
                            Text("Test", color = TextPrimary)
                        }
                    }

                    Button(
                        onClick = {
                            onSaveURL(inputURL)
                            onDismiss()
                        },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = BluePrimary),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        Text("Save & Connect", color = TextPrimary)
                    }
                }

                if (testResult != null) {
                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = if (testResult == true) "Connection successful!" else "Connection failed.",
                        color = if (testResult == true) GreenActive else RedLive,
                        style = MaterialTheme.typography.labelSmall
                    )
                }

                Spacer(modifier = Modifier.height(20.dp))
                Divider(color = DarkBorder)
                Spacer(modifier = Modifier.height(16.dp))

                // Discovered Servers
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Discovered Servers (LAN)",
                        style = MaterialTheme.typography.titleMedium.copy(color = TextSecondary, fontSize = 14.sp)
                    )
                    IconButton(onClick = { serverDiscovery.startDiscovery() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Scan", tint = TextSecondary)
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                if (isSearching && discoveredServers.isEmpty()) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.padding(vertical = 12.dp)
                    ) {
                        CircularProgressIndicator(color = BluePrimary, modifier = Modifier.size(18.dp))
                        Text("Searching via mDNS...", style = MaterialTheme.typography.labelSmall.copy(color = TextMuted))
                    }
                } else if (discoveredServers.isEmpty()) {
                    Text("No HDHR Open servers found on LAN.", style = MaterialTheme.typography.labelSmall.copy(color = TextMuted))
                } else {
                    LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        items(discoveredServers, key = { it.id }) { server ->
                            Card(
                                shape = RoundedCornerShape(10.dp),
                                colors = CardDefaults.cardColors(containerColor = DarkSurfaceVariant),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        inputURL = server.url
                                        onSaveURL(server.url)
                                        onDismiss()
                                    }
                            ) {
                                Row(
                                    modifier = Modifier.padding(12.dp).fillMaxWidth(),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(Icons.Default.Dns, contentDescription = "Server", tint = BluePrimary)
                                    Spacer(modifier = Modifier.width(10.dp))
                                    Column {
                                        Text(server.name, style = MaterialTheme.typography.titleMedium.copy(color = TextPrimary, fontSize = 14.sp))
                                        Text(server.url, style = MaterialTheme.typography.labelSmall.copy(color = TextSecondary))
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
