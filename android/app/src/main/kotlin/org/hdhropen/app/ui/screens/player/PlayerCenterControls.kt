package org.hdhropen.app.ui.screens.player

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Forward10
import androidx.compose.material.icons.filled.PauseCircle
import androidx.compose.material.icons.filled.PlayCircle
import androidx.compose.material.icons.filled.Replay10
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

@Composable
fun PlayerCenterControls(
    isPlaying: Boolean,
    isSeekable: Boolean,
    onPlayPause: () -> Unit,
    onSkipBackward: () -> Unit,
    onSkipForward: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(40.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (isSeekable) {
            IconButton(
                onClick = onSkipBackward,
                modifier = Modifier.size(52.dp)
            ) {
                Icon(
                    Icons.Default.Replay10,
                    contentDescription = "Skip Back 10s",
                    tint = Color.White,
                    modifier = Modifier.size(36.dp)
                )
            }
        }

        IconButton(
            onClick = onPlayPause,
            modifier = Modifier.size(72.dp)
        ) {
            Icon(
                if (isPlaying) Icons.Default.PauseCircle else Icons.Default.PlayCircle,
                contentDescription = "Play/Pause",
                tint = Color.White,
                modifier = Modifier.size(68.dp)
            )
        }

        if (isSeekable) {
            IconButton(
                onClick = onSkipForward,
                modifier = Modifier.size(52.dp)
            ) {
                Icon(
                    Icons.Default.Forward10,
                    contentDescription = "Skip Forward 10s",
                    tint = Color.White,
                    modifier = Modifier.size(36.dp)
                )
            }
        }
    }
}
