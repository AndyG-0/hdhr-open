package org.hdhropen.app.ui.screens.recordings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.viewmodels.RecordingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecordingDetailBottomSheet(
    recording: HDHomeRunRecording,
    recordingsViewModel: RecordingsViewModel,
    onDismiss: () -> Unit,
    onPlay: () -> Unit
) {
    val coroutineScope = rememberCoroutineScope()

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = MaterialTheme.colorScheme.surface,
        scrimColor = MaterialTheme.colorScheme.background.copy(alpha = 0.6f),
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 12.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text(
                text = recording.title,
                style = MaterialTheme.typography.titleLarge.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
            )

            if (!recording.episodeTitle.isNullOrEmpty() || recording.episodeDesignation != null) {
                Spacer(modifier = Modifier.height(4.dp))
                val epStr = buildString {
                    recording.episodeDesignation?.let { append(it) }
                    if (recording.episodeDesignation != null && !recording.episodeTitle.isNullOrEmpty()) append(" • ")
                    recording.episodeTitle?.let { append(it) }
                }
                Text(
                    text = epStr,
                    style = MaterialTheme.typography.bodyMedium.copy(color = YellowAccent)
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Badges Row
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (recording.formattedDuration.isNotEmpty()) {
                    Text(
                        text = recording.formattedDuration,
                        style = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                    )
                }
                if (recording.formattedFileSize.isNotEmpty()) {
                    Text(
                        text = "• ${recording.formattedFileSize}",
                        style = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                    )
                }
                if (!recording.channelName.isNullOrEmpty()) {
                    Text(
                        text = "• ${recording.channelName}",
                        style = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                    )
                }
            }

            if (!recording.synopsis.isNullOrEmpty()) {
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = recording.synopsis ?: "",
                    style = MaterialTheme.typography.bodyMedium.copy(
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        lineHeight = 20.sp
                    )
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Play Action Button
            Button(
                onClick = {
                    onPlay()
                    onDismiss()
                },
                modifier = Modifier.fillMaxWidth().height(48.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = BluePrimary)
            ) {
                Icon(Icons.Default.PlayArrow, contentDescription = "Play", tint = MaterialTheme.colorScheme.onSurface)
                Spacer(modifier = Modifier.width(8.dp))
                Text("Play Recording", style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 15.sp))
            }

            if (!recording.isInProgress) {
                Spacer(modifier = Modifier.height(12.dp))

                // Delete Action Button
                OutlinedButton(
                    onClick = {
                        coroutineScope.launch {
                            recordingsViewModel.deleteRecording(recording)
                            onDismiss()
                        }
                    },
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = RedLive)
                ) {
                    Icon(Icons.Default.Delete, contentDescription = "Delete", tint = RedLive)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Delete Recording", color = RedLive)
                }
            }

            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}
