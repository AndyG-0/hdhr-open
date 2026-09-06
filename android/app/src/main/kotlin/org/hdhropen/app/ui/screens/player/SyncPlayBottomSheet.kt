package org.hdhropen.app.ui.screens.player

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.media3.common.util.UnstableApi
import org.hdhropen.app.ui.theme.BluePrimary
import org.hdhropen.app.ui.theme.RedLive
import org.hdhropen.app.ui.theme.YellowAccent
import org.hdhropen.kit.models.SyncPlayParticipant
import org.hdhropen.kit.viewmodels.PlayerViewModel

@OptIn(ExperimentalMaterial3Api::class)
@UnstableApi
@Composable
fun SyncPlayBottomSheet(
    playerViewModel: PlayerViewModel,
    onDismiss: () -> Unit
) {
    val room by playerViewModel.syncPlayRoom.collectAsState()
    val participants by playerViewModel.syncPlayParticipants.collectAsState()
    val isHost by playerViewModel.isSyncPlayHost.collectAsState()
    val isConnected by playerViewModel.syncPlayConnected.collectAsState()
    val mySessionId by playerViewModel.syncPlayClient.sessionId.collectAsState()

    var userName by remember { mutableStateOf("Android User") }
    var roomCodeInput by remember { mutableStateOf("") }
    var isBusy by remember { mutableStateOf(false) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var copiedToClipboard by remember { mutableStateOf(false) }

    val clipboardManager = LocalClipboardManager.current

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 12.dp)
        ) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Default.Group,
                        contentDescription = "SyncPlay",
                        tint = BluePrimary,
                        modifier = Modifier.size(28.dp)
                    )
                    Spacer(Modifier.width(10.dp))
                    Text(
                        text = "SyncPlay Watch Party",
                        style = MaterialTheme.typography.titleLarge.copy(
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                    )
                }
                IconButton(onClick = onDismiss) {
                    Icon(Icons.Default.Close, contentDescription = "Close")
                }
            }

            Spacer(Modifier.height(16.dp))

            errorMessage?.let { err ->
                Card(
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp)
                ) {
                    Text(
                        text = err,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(12.dp)
                    )
                }
            }

            if (room != null && isConnected) {
                // Active Room State
                val activeRoom = room!!
                Card(
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text(
                                    text = "ROOM CODE",
                                    style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                                )
                                Text(
                                    text = activeRoom.roomCode,
                                    style = MaterialTheme.typography.headlineMedium.copy(
                                        fontWeight = FontWeight.Black,
                                        letterSpacing = 4.sp,
                                        color = BluePrimary
                                    )
                                )
                            }
                            Button(
                                onClick = {
                                    clipboardManager.setText(AnnotatedString(activeRoom.roomCode))
                                    copiedToClipboard = true
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.surface)
                            ) {
                                Icon(
                                    if (copiedToClipboard) Icons.Default.Check else Icons.Default.ContentCopy,
                                    contentDescription = "Copy",
                                    tint = MaterialTheme.colorScheme.onSurface,
                                    modifier = Modifier.size(18.dp)
                                )
                                Spacer(Modifier.width(6.dp))
                                Text(
                                    if (copiedToClipboard) "Copied!" else "Copy",
                                    color = MaterialTheme.colorScheme.onSurface
                                )
                            }
                        }

                        val currentContent = activeRoom.content
                        if (currentContent != null) {
                            Spacer(Modifier.height(12.dp))
                            HorizontalDivider()
                            Spacer(Modifier.height(8.dp))
                            Text(
                                text = "Playing: ${if (currentContent.title.isNotEmpty()) currentContent.title else currentContent.channelNumber ?: "Live"}",
                                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold)
                            )
                        }
                    }
                }

                Spacer(Modifier.height(16.dp))

                // Participants List
                Text(
                    text = "Participants (${participants.size})",
                    style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold)
                )
                Spacer(Modifier.height(8.dp))

                LazyColumn(
                    modifier = Modifier.weight(1f, fill = false).heightIn(max = 240.dp)
                ) {
                    items(participants, key = { it.sessionId }) { participant ->
                        ParticipantRow(
                            participant = participant,
                            isMe = participant.sessionId == mySessionId,
                            canTransferHost = isHost && participant.sessionId != mySessionId,
                            onMakeHost = { playerViewModel.transferSyncPlayHost(participant.sessionId) }
                        )
                    }
                }

                Spacer(Modifier.height(20.dp))

                Button(
                    onClick = {
                        playerViewModel.leaveSyncPlayRoom()
                        onDismiss()
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = RedLive),
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Icon(Icons.Default.ExitToApp, contentDescription = null, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("Leave Watch Party", fontWeight = FontWeight.Bold)
                }
            } else {
                // Not Connected - Join or Create UI
                OutlinedTextField(
                    value = userName,
                    onValueChange = { userName = it },
                    label = { Text("Your Display Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                )

                Spacer(Modifier.height(16.dp))

                OutlinedTextField(
                    value = roomCodeInput,
                    onValueChange = { if (it.length <= 6) roomCodeInput = it.uppercase() },
                    label = { Text("Room Code") },
                    placeholder = { Text("6-letter code") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                )

                Spacer(Modifier.height(16.dp))

                Button(
                    onClick = {
                        if (roomCodeInput.length == 6 && userName.isNotBlank()) {
                            isBusy = true
                            errorMessage = null
                            playerViewModel.joinSyncPlayRoom(roomCodeInput, userName) { result ->
                                isBusy = false
                                if (result.isFailure) {
                                    errorMessage = result.exceptionOrNull()?.localizedMessage ?: "Failed to join room"
                                }
                            }
                        }
                    },
                    enabled = roomCodeInput.length == 6 && userName.isNotBlank() && !isBusy,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Text("Join Party", fontWeight = FontWeight.Bold)
                }

                Spacer(Modifier.height(16.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    HorizontalDivider(modifier = Modifier.weight(1f))
                    Text(
                        text = "OR",
                        style = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant),
                        modifier = Modifier.padding(horizontal = 12.dp)
                    )
                    HorizontalDivider(modifier = Modifier.weight(1f))
                }

                Spacer(Modifier.height(16.dp))

                OutlinedButton(
                    onClick = {
                        if (userName.isNotBlank()) {
                            isBusy = true
                            errorMessage = null
                            playerViewModel.createSyncPlayRoom(userName) { result ->
                                isBusy = false
                                if (result.isFailure) {
                                    errorMessage = result.exceptionOrNull()?.localizedMessage ?: "Failed to create room"
                                }
                            }
                        }
                    },
                    enabled = userName.isNotBlank() && !isBusy,
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Text("Create New Watch Party", fontWeight = FontWeight.Bold)
                }
            }

            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun ParticipantRow(
    participant: SyncPlayParticipant,
    isMe: Boolean,
    canTransferHost: Boolean,
    onMakeHost: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(CircleShape)
                    .background(BluePrimary.copy(alpha = 0.2f)),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = participant.userName.take(1).uppercase(),
                    style = MaterialTheme.typography.titleMedium.copy(
                        color = BluePrimary,
                        fontWeight = FontWeight.Bold
                    )
                )
            }
            Spacer(Modifier.width(12.dp))
            Column {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = participant.userName + if (isMe) " (You)" else "",
                        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium)
                    )
                    if (participant.isHost) {
                        Spacer(Modifier.width(6.dp))
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(YellowAccent.copy(alpha = 0.25f))
                                .padding(horizontal = 6.dp, vertical = 2.dp)
                        ) {
                            Text(
                                text = "HOST",
                                style = MaterialTheme.typography.labelSmall.copy(
                                    color = YellowAccent,
                                    fontWeight = FontWeight.Bold
                                )
                            )
                        }
                    }
                }
                participant.pingMs?.let { ping ->
                    Text(
                        text = "${ping.toInt()} ms",
                        style = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                    )
                }
            }
        }

        if (canTransferHost) {
            TextButton(onClick = onMakeHost) {
                Text("Make Host", style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}
