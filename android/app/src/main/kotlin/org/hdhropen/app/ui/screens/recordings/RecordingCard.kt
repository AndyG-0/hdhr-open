package org.hdhropen.app.ui.screens.recordings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunRecording

@Composable
fun RecordingCard(
    recording: HDHomeRunRecording,
    onClick: () -> Unit
) {
    Card(
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .clickable { onClick() }
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Thumbnail / Icon Box
            Box(
                modifier = Modifier
                    .size(64.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    Icons.Default.Movie,
                    contentDescription = "Recording",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(32.dp)
                )

                if (recording.isInProgress) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(4.dp)
                            .clip(RoundedCornerShape(4.dp))
                            .background(RedLive)
                            .padding(horizontal = 4.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "REC",
                            style = MaterialTheme.typography.labelSmall.copy(
                                color = MaterialTheme.colorScheme.onSurface,
                                fontSize = 9.sp,
                                fontWeight = FontWeight.Bold
                            )
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.width(12.dp))

            // Details
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = recording.title,
                    style = MaterialTheme.typography.titleMedium.copy(
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    ),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )

                if (!recording.episodeTitle.isNullOrEmpty() || recording.episodeDesignation != null) {
                    Spacer(modifier = Modifier.height(2.dp))
                    val epStr = buildString {
                        recording.episodeDesignation?.let { append(it) }
                        if (recording.episodeDesignation != null && !recording.episodeTitle.isNullOrEmpty()) append(" • ")
                        recording.episodeTitle?.let { append(it) }
                    }
                    Text(
                        text = epStr,
                        style = MaterialTheme.typography.bodySmall.copy(color = YellowAccent),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }

                Spacer(modifier = Modifier.height(4.dp))

                DvrProviderBadge(provider = recording.provider)

                Spacer(modifier = Modifier.height(4.dp))

                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (recording.formattedDuration.isNotEmpty()) {
                        Text(
                            text = recording.formattedDuration,
                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                        )
                    }

                    if (recording.formattedFileSize.isNotEmpty()) {
                        Text(
                            text = "•",
                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted)
                        )
                        Text(
                            text = recording.formattedFileSize,
                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                        )
                    }

                    if (!recording.channelName.isNullOrEmpty()) {
                        Text(
                            text = "•",
                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted)
                        )
                        Text(
                            text = recording.channelName ?: "",
                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted),
                            maxLines = 1
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun DvrProviderBadge(provider: String?) {
    val (label, color) = when (provider) {
        "hdhomerun" -> "HDHomeRun DVR" to GreenActive
        "builtin" -> "Built-in DVR" to BluePrimary
        else -> return
    }
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .border(1.dp, color, RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 1.dp)
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall.copy(
                color = color,
                fontSize = 9.sp,
                fontWeight = FontWeight.Bold
            )
        )
    }
}
