package org.hdhropen.app.ui.screens.player

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
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
import androidx.compose.ui.platform.testTag
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
    modifier: Modifier = Modifier,
    onScrubbingStateChange: ((Boolean) -> Unit)? = null
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

    Column(modifier = modifier.fillMaxWidth()) {
        // Thumbnail / Time Preview Bubble if dragging
        if (isDragging) {
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
                .height(32.dp)
                .testTag("ScrubBarTrack")
                .pointerInput(isSeekable, duration) {
                    if (!isSeekable || duration <= 0.0) return@pointerInput
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        down.consume()
                        isDragging = true
                        onScrubbingStateChange?.invoke(true)
                        var currentRatio = (down.position.x / size.width).coerceIn(0f, 1f)
                        dragPositionRatio = currentRatio

                        try {
                            while (true) {
                                val event = awaitPointerEvent()
                                val change = event.changes.firstOrNull { it.id == down.id } ?: break
                                change.consume()
                                if (!change.pressed) {
                                    val target = currentRatio.toDouble() * duration
                                    onSeek(target)
                                    break
                                }
                                currentRatio = (change.position.x / size.width).coerceIn(0f, 1f)
                                dragPositionRatio = currentRatio
                            }
                        } finally {
                            isDragging = false
                            onScrubbingStateChange?.invoke(false)
                        }
                    }
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
