package org.hdhropen.app.ui.screens.player

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.hdhropen.kit.models.HDHomeRunRecordingAudioInfo
import org.hdhropen.kit.models.HDHomeRunRecordingVideoInfo
import org.hdhropen.kit.models.HDHomeRunTranscodeInfo
import org.hdhropen.kit.viewmodels.PlaybackMode

@Composable
fun PlaybackInfoDialog(
    playbackMode: PlaybackMode?,
    transcodeInfo: HDHomeRunTranscodeInfo?,
    videoSpecs: HDHomeRunRecordingVideoInfo?,
    audioTracks: List<HDHomeRunRecordingAudioInfo>,
    observedBitrateBps: Long?,
    onDismiss: () -> Unit
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.6f))
    ) {
        Card(
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            modifier = Modifier
                .align(Alignment.Center)
                .padding(32.dp)
                .widthIn(max = 420.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Playback Info",
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold)
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close")
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                InfoRow(label = "Playback", value = playbackModeLabel(playbackMode, transcodeInfo))

                videoSpecs?.let { specs ->
                    SectionHeading("Video")
                    specs.codec?.let { InfoRow(label = "Codec", value = it.uppercase()) }
                    if (specs.width != null && specs.height != null) {
                        InfoRow(label = "Resolution", value = "${specs.width}×${specs.height}")
                    }
                    specs.fps?.let { InfoRow(label = "Framerate", value = "${it.toInt()} fps") }
                }

                if (audioTracks.isNotEmpty()) {
                    SectionHeading("Audio")
                    audioTracks.forEach { track ->
                        InfoRow(
                            label = "Track ${track.index + 1}",
                            value = "${track.codec?.uppercase() ?: "?"} · ${track.channels ?: "?"}ch"
                        )
                    }
                }

                observedBitrateBps?.let { bps ->
                    SectionHeading("Network")
                    InfoRow(label = "Bitrate", value = "%.1f Mbps".format(bps / 1_000_000.0))
                }
            }
        }
    }
}

private fun playbackModeLabel(mode: PlaybackMode?, transcodeInfo: HDHomeRunTranscodeInfo?): String {
    return when (mode) {
        PlaybackMode.Direct -> "Direct (client-side)"
        PlaybackMode.ServerTranscodedHls -> {
            val presetLabel = transcodeInfo?.presetLabel
            if (presetLabel != null) {
                "Server transcoded via $presetLabel" + if (transcodeInfo.hardware) " (HW)" else ""
            } else {
                "Server transcoded (HLS)"
            }
        }
        null -> "Unknown"
    }
}

@Composable
private fun SectionHeading(text: String) {
    Spacer(modifier = Modifier.height(12.dp))
    Text(
        text = text,
        style = MaterialTheme.typography.labelLarge.copy(
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontWeight = FontWeight.Bold
        )
    )
    Spacer(modifier = Modifier.height(4.dp))
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(text = label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(text = value, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
    }
}
