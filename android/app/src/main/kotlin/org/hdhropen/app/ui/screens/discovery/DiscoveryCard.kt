package org.hdhropen.app.ui.screens.discovery

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Explore
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
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.utilities.TimeFormatting

// Mirrors the web client's discovery.* source labels - shown on every
// non-"personalized" item so users can see why something was recommended.
private fun sourceBadgeLabel(source: String?): String? = when (source) {
    "active_rule" -> "Active rule"
    "favorite_team" -> "Favorite team"
    "network_pick" -> "Network pick"
    "new_and_notable" -> "New & notable"
    else -> null
}

// Text-only card for a recommended upcoming airing - no image-loading
// library exists anywhere in this app (imageUrl is only ever read for
// Media3 notification artwork), so poster art is explicitly out of scope
// here. Visual treatment mirrors RecordingCard: bordered Card, a static
// icon box in place of artwork, and the same typography scale.
@Composable
fun DiscoveryCard(
    item: HDHomeRunGuideEntry,
    channel: HDHomeRunChannel?,
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
            // Icon box in place of artwork (no image-loading library in this app)
            Box(
                modifier = Modifier
                    .size(64.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    Icons.Default.Explore,
                    contentDescription = "Discovery",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(32.dp)
                )

                if (item.isNew == true) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(4.dp)
                            .clip(RoundedCornerShape(4.dp))
                            .background(GreenActive)
                            .padding(horizontal = 4.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "NEW",
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

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = item.title,
                    style = MaterialTheme.typography.titleMedium.copy(
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    ),
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )

                val epDesignation = item.formattedEpisodeDesignation
                if (!epDesignation.isNullOrEmpty() || !item.episodeTitle.isNullOrEmpty()) {
                    Spacer(modifier = Modifier.height(2.dp))
                    val epStr = buildString {
                        if (!epDesignation.isNullOrEmpty()) append(epDesignation)
                        if (!epDesignation.isNullOrEmpty() && !item.episodeTitle.isNullOrEmpty()) append(" • ")
                        item.episodeTitle?.let { append(it) }
                    }
                    Text(
                        text = epStr,
                        style = MaterialTheme.typography.bodySmall.copy(color = YellowAccent),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }

                if (!item.category.isNullOrEmpty()) {
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = item.category ?: "",
                        style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }

                val badgeLabel = sourceBadgeLabel(item.source)
                if (badgeLabel != null) {
                    Spacer(modifier = Modifier.height(4.dp))
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .background(MaterialTheme.colorScheme.surfaceVariant)
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = badgeLabel,
                            style = MaterialTheme.typography.labelSmall.copy(
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                fontSize = 10.sp
                            )
                        )
                    }
                }

                Spacer(modifier = Modifier.height(4.dp))

                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    val timeStr = TimeFormatting.formatTimeRange(item.start, item.end)
                    if (timeStr.isNotEmpty()) {
                        Text(
                            text = timeStr,
                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                        )
                    }

                    val channelLabel = channel?.let { "${it.channelNumber} ${it.name}".trim() }
                        ?: item.channelNumber
                    if (!channelLabel.isNullOrEmpty()) {
                        Text(
                            text = "•",
                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted)
                        )
                        Text(
                            text = channelLabel,
                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
            }
        }
    }
}
