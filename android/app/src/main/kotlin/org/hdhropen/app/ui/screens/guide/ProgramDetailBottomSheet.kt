package org.hdhropen.app.ui.screens.guide

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.StarOutline
import androidx.compose.material.icons.filled.VideoLibrary
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.utilities.TimeFormatting
import org.hdhropen.kit.viewmodels.GuideViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProgramDetailBottomSheet(
    channel: HDHomeRunChannel,
    airing: HDHomeRunGuideEntry,
    guideViewModel: GuideViewModel,
    onDismiss: () -> Unit,
    onTune: () -> Unit
) {
    val coroutineScope = rememberCoroutineScope()
    val recordingRules by guideViewModel.recordingRules.collectAsState()
    val favoriteChannels by guideViewModel.favoriteChannels.collectAsState()

    val isFav = favoriteChannels.contains(channel.channelNumber)
    val existingRule = remember(recordingRules, channel, airing) {
        guideViewModel.findRule(channel.channelNumber, airing)
    }

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
            // Channel Header & Favorite
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = channel.channelNumber,
                        style = MaterialTheme.typography.titleMedium.copy(
                            color = BluePrimary,
                            fontWeight = FontWeight.Bold
                        )
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = channel.name,
                        style = MaterialTheme.typography.bodyMedium.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                    )
                    if (channel.isHD) {
                        Spacer(modifier = Modifier.width(6.dp))
                        Surface(
                            color = BluePrimary.copy(alpha = 0.85f),
                            shape = RoundedCornerShape(3.dp)
                        ) {
                            Text(
                                text = "HD",
                                style = MaterialTheme.typography.labelSmall.copy(
                                    color = Color.White,
                                    fontSize = 9.sp,
                                    fontWeight = FontWeight.Bold
                                ),
                                modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                            )
                        }
                    }
                }

                IconButton(onClick = { guideViewModel.toggleFavorite(channel.channelNumber) }) {
                    Icon(
                        if (isFav) Icons.Default.Star else Icons.Default.StarOutline,
                        contentDescription = "Favorite",
                        tint = if (isFav) YellowAccent else MaterialTheme.extendedColors.textMuted
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Airing Title
            Text(
                text = airing.title,
                style = MaterialTheme.typography.titleLarge.copy(
                    color = MaterialTheme.colorScheme.onSurface,
                    fontWeight = FontWeight.Bold
                )
            )

            // Episode / Season
            if (!airing.episodeTitle.isNullOrEmpty() || !airing.episodeNumber.isNullOrEmpty()) {
                Spacer(modifier = Modifier.height(4.dp))
                val epText = buildString {
                    airing.episodeNumber?.let { append("Ep $it") }
                    if (!airing.episodeNumber.isNullOrEmpty() && !airing.episodeTitle.isNullOrEmpty()) append(" • ")
                    airing.episodeTitle?.let { append(it) }
                }
                Text(
                    text = epText,
                    style = MaterialTheme.typography.bodyMedium.copy(color = YellowAccent)
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Time & Date
            Text(
                text = TimeFormatting.formatTimeRange(airing.start, airing.end),
                style = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
            )

            // Synopsis
            if (!airing.synopsis.isNullOrEmpty()) {
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = airing.synopsis ?: "",
                    style = MaterialTheme.typography.bodyMedium.copy(
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        lineHeight = 20.sp
                    )
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Actions
            Button(
                onClick = {
                    onTune()
                    onDismiss()
                },
                modifier = Modifier.fillMaxWidth().height(48.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = BluePrimary)
            ) {
                Icon(Icons.Default.PlayArrow, contentDescription = "Tune Channel", tint = MaterialTheme.colorScheme.onSurface)
                Spacer(modifier = Modifier.width(8.dp))
                Text("Tune Channel ${channel.channelNumber}", style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 15.sp))
            }

            Spacer(modifier = Modifier.height(12.dp))

            if (existingRule != null) {
                OutlinedButton(
                    onClick = {
                        coroutineScope.launch {
                            guideViewModel.cancelRule(existingRule.recordingRuleId)
                        }
                    },
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.outlinedButtonColors(contentColor = RedLive)
                ) {
                    Icon(Icons.Default.FiberManualRecord, contentDescription = "Cancel", tint = RedLive)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Cancel Recording (${if (existingRule.isSeriesRule) "Series" else "Episode"})", color = RedLive)
                }
            } else {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Record Episode
                    Button(
                        onClick = {
                            coroutineScope.launch {
                                guideViewModel.recordEpisode(
                                    seriesId = airing.seriesId,
                                    channelNumber = channel.channelNumber,
                                    start = airing.start
                                )
                            }
                        },
                        modifier = Modifier.weight(1f).height(48.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
                    ) {
                        Icon(Icons.Default.FiberManualRecord, contentDescription = "Record Episode", tint = RedLive)
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Record Ep", color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.labelMedium)
                    }

                    // Record Series
                    val seriesId = airing.seriesId
                    if (!seriesId.isNullOrEmpty()) {
                        Button(
                            onClick = {
                                coroutineScope.launch {
                                    guideViewModel.recordSeries(
                                        seriesId = seriesId,
                                        channelNumber = channel.channelNumber
                                    )
                                }
                            },
                            modifier = Modifier.weight(1f).height(48.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
                        ) {
                            Icon(Icons.Default.VideoLibrary, contentDescription = "Record Series", tint = YellowAccent)
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("Record Series", color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.labelMedium)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}
