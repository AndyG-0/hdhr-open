package org.hdhropen.app.ui.screens.player

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.hdhropen.app.ui.theme.BluePrimary
import org.hdhropen.app.ui.theme.GreenActive
import org.hdhropen.app.ui.theme.RedLive
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.models.HDHomeRunRecordingAudioInfo
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import org.hdhropen.kit.playback.ThumbnailCue

@Composable
fun PlayerBottomBar(
    currentTime: Double,
    duration: Double,
    isLive: Boolean,
    isSeekable: Boolean,
    thumbnailCues: List<ThumbnailCue>,
    isWatchSession: Boolean,
    isPromoted: Boolean,
    isPromoting: Boolean,
    existingRule: HDHomeRunRecordingRule?,
    activeAiring: HDHomeRunGuideEntry?,
    availableAudioTracks: List<HDHomeRunRecordingAudioInfo>,
    currentAudioTrack: HDHomeRunRecordingAudioInfo?,
    isSwitchingAudioTrack: Boolean,
    onSeek: (Double) -> Unit,
    onScrubbingStateChange: (Boolean) -> Unit,
    onPromoteToRecording: () -> Unit,
    onRecordEpisode: () -> Unit,
    onRecordSeries: () -> Unit,
    onCancelRule: (String) -> Unit,
    onOpenRecordingOptions: () -> Unit,
    onSelectAudioTrack: (HDHomeRunRecordingAudioInfo) -> Unit,
    modifier: Modifier = Modifier
) {
    var showRecordMenu by remember { mutableStateOf(false) }
    var showAudioMenu by remember { mutableStateOf(false) }

    Column(
        modifier = modifier
            .navigationBarsPadding()
            .padding(horizontal = 20.dp, vertical = 20.dp)
    ) {
        ScrubBar(
            currentTime = currentTime,
            duration = duration,
            isLive = isLive,
            isSeekable = isSeekable,
            thumbnailCues = thumbnailCues,
            onSeek = onSeek,
            onScrubbingStateChange = onScrubbingStateChange
        )

        Spacer(modifier = Modifier.height(12.dp))

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
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
                                    onCancelRule(existingRule.recordingRuleId)
                                }
                            )
                            DropdownMenuItem(
                                text = { Text("Recording Options…") },
                                onClick = {
                                    showRecordMenu = false
                                    onOpenRecordingOptions()
                                }
                            )
                        } else {
                            DropdownMenuItem(
                                text = { Text(if (isPromoted) "Recording Saved" else "Save Current Recording") },
                                enabled = !isPromoted && !isPromoting,
                                onClick = {
                                    showRecordMenu = false
                                    onPromoteToRecording()
                                }
                            )
                            DropdownMenuItem(
                                text = { Text("Record Episode") },
                                onClick = {
                                    showRecordMenu = false
                                    onRecordEpisode()
                                }
                            )
                            if (!activeAiring?.seriesId.isNullOrEmpty() || !activeAiring?.title.isNullOrEmpty()) {
                                DropdownMenuItem(
                                    text = { Text("Record Series") },
                                    onClick = {
                                        showRecordMenu = false
                                        onRecordSeries()
                                    }
                                )
                            }
                            DropdownMenuItem(
                                text = { Text("Recording Options…") },
                                onClick = {
                                    showRecordMenu = false
                                    onOpenRecordingOptions()
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
                                    onSelectAudioTrack(track)
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
