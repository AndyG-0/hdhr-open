package org.hdhropen.app.ui.screens.player

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ClosedCaption
import androidx.compose.material.icons.filled.Group
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.PictureInPictureAlt
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.mediarouter.app.MediaRouteButton
import com.google.android.gms.cast.framework.CastButtonFactory
import org.hdhropen.app.ui.theme.BluePrimary
import org.hdhropen.app.ui.theme.YellowAccent
import org.hdhropen.kit.models.SyncPlayParticipant
import org.hdhropen.kit.models.SyncPlayRoom

@Composable
fun PlayerTopBar(
    title: String,
    subtitle: String?,
    isCasting: Boolean,
    syncPlayRoom: SyncPlayRoom?,
    syncPlayParticipants: List<SyncPlayParticipant>,
    isCaptionsEnabled: Boolean,
    onToggleCaptions: () -> Unit,
    onOpenSyncPlay: () -> Unit,
    onOpenPlaybackInfo: () -> Unit,
    onEnterPip: () -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .statusBarsPadding()
            .padding(horizontal = 16.dp, vertical = 20.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        IconButton(onClick = onClose) {
            Icon(
                Icons.Default.KeyboardArrowDown,
                contentDescription = "Close",
                tint = Color.White,
                modifier = Modifier.size(36.dp)
            )
        }

        Column(
            modifier = Modifier.weight(1f).padding(horizontal = 8.dp),
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.titleMedium.copy(
                    color = Color.White,
                    fontWeight = FontWeight.Bold
                ),
                maxLines = 1
            )
            if (isCasting) {
                Text(
                    text = "Casting to TV",
                    style = MaterialTheme.typography.bodySmall.copy(color = YellowAccent),
                    maxLines = 1
                )
            } else {
                subtitle?.let { sub ->
                    Text(
                        text = sub,
                        style = MaterialTheme.typography.bodySmall.copy(color = Color.White.copy(alpha = 0.8f)),
                        maxLines = 1
                    )
                }
            }
        }

        // Cast Button
        AndroidView(
            factory = { ctx ->
                try {
                    val themedContext = android.view.ContextThemeWrapper(
                        ctx,
                        androidx.appcompat.R.style.Theme_AppCompat_NoActionBar
                    )
                    MediaRouteButton(themedContext).apply {
                        runCatching { CastButtonFactory.setUpMediaRouteButton(themedContext, this) }
                    }
                } catch (e: Throwable) {
                    android.view.View(ctx)
                }
            },
            modifier = Modifier.size(48.dp)
        )

        // SyncPlay Watch Party Toggle
        IconButton(onClick = onOpenSyncPlay) {
            BadgedBox(
                badge = {
                    if (syncPlayRoom != null && syncPlayParticipants.isNotEmpty()) {
                        Badge(containerColor = BluePrimary) {
                            Text(syncPlayParticipants.size.toString())
                        }
                    }
                }
            ) {
                Icon(
                    Icons.Default.Group,
                    contentDescription = "SyncPlay Watch Party",
                    tint = if (syncPlayRoom != null) BluePrimary else Color.White
                )
            }
        }

        // Playback Info Toggle
        IconButton(onClick = onOpenPlaybackInfo) {
            Icon(
                Icons.Default.Info,
                contentDescription = "Playback Info",
                tint = Color.White
            )
        }

        // Captions Toggle
        IconButton(onClick = onToggleCaptions) {
            Icon(
                Icons.Default.ClosedCaption,
                contentDescription = "Captions",
                tint = if (isCaptionsEnabled) YellowAccent else Color.White
            )
        }

        // Picture-in-Picture Toggle
        if (!isCasting) {
            IconButton(onClick = onEnterPip) {
                Icon(
                    Icons.Default.PictureInPictureAlt,
                    contentDescription = "Picture-in-Picture",
                    tint = Color.White
                )
            }
        }
    }
}
