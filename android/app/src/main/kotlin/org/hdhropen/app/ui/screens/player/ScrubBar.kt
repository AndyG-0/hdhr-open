package org.hdhropen.app.ui.screens.player

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.playback.ThumbnailCue
import org.hdhropen.kit.utilities.TimeFormatting

@Composable
fun ScrubBar(
    currentTime: Double,
    duration: Double,
    isLive: Boolean,
    isSeekable: Boolean,
    thumbnailCues: List<ThumbnailCue>,
    onSeek: (Double) -> Unit,
    modifier: Modifier = Modifier
) {
    var isDragging by remember { mutableStateOf(false) }
    var dragPositionRatio by remember { mutableFloatStateOf(0f) }

    val effectiveRatio = if (isDragging) {
        dragPositionRatio
    } else if (duration > 0) {
        (currentTime / duration).toFloat().coerceIn(0f, 1f)
    } else {
        0f
    }

    val previewTime = if (duration > 0) effectiveRatio.toDouble() * duration else currentTime

    val activeThumbnail = remember(previewTime, thumbnailCues) {
        thumbnailCues.firstOrNull { it.contains(previewTime) }
    }

    Column(modifier = modifier.fillMaxWidth()) {
        // Thumbnail Preview Bubble if dragging
        if (isDragging && activeThumbnail != null) {
            Box(
                modifier = Modifier
                    .padding(bottom = 8.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .padding(horizontal = 8.dp, vertical = 4.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = TimeFormatting.formatSecondsToClock(previewTime),
                    style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurface, fontSize = 11.sp)
                )
            }
        }

        // Scrub Bar Canvas
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(24.dp)
                .pointerInput(isSeekable, duration) {
                    if (!isSeekable) return@pointerInput
                    detectTapGestures { offset ->
                        val ratio = (offset.x / size.width).coerceIn(0f, 1f)
                        val target = ratio.toDouble() * duration
                        onSeek(target)
                    }
                }
                .pointerInput(isSeekable, duration) {
                    if (!isSeekable) return@pointerInput
                    detectDragGestures(
                        onDragStart = { offset ->
                            isDragging = true
                            dragPositionRatio = (offset.x / size.width).coerceIn(0f, 1f)
                        },
                        onDragEnd = {
                            val target = dragPositionRatio.toDouble() * duration
                            onSeek(target)
                            isDragging = false
                        },
                        onDragCancel = { isDragging = false },
                        onDrag = { change, _ ->
                            dragPositionRatio = (change.position.x / size.width).coerceIn(0f, 1f)
                        }
                    )
                },
            contentAlignment = Alignment.CenterStart
        ) {
            Canvas(modifier = Modifier.fillMaxWidth().height(4.dp)) {
                val barWidth = size.width
                val barHeight = size.height

                // Background track
                drawRect(
                    color = Color.White.copy(alpha = 0.3f),
                    size = size
                )

                // Played track
                drawRect(
                    color = if (isLive) RedLive else BluePrimary,
                    size = androidx.compose.ui.geometry.Size(barWidth * effectiveRatio, barHeight)
                )

                // Thumb circle
                if (isSeekable) {
                    drawCircle(
                        color = Color.White,
                        radius = if (isDragging) 8.dp.toPx() else 6.dp.toPx(),
                        center = Offset(barWidth * effectiveRatio, barHeight / 2)
                    )
                }
            }
        }

        // Time Labels
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = TimeFormatting.formatSecondsToClock(previewTime),
                style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
            )

            if (isLive) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(6.dp)
                            .clip(RoundedCornerShape(3.dp))
                            .background(RedLive)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "LIVE",
                        style = MaterialTheme.typography.labelSmall.copy(
                            color = RedLive,
                            fontWeight = FontWeight.Bold
                        )
                    )
                }
            } else if (duration > 0) {
                Text(
                    text = TimeFormatting.formatSecondsToClock(duration),
                    style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                )
            }
        }
    }
}
