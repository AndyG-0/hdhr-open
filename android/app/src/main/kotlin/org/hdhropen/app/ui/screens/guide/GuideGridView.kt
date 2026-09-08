package org.hdhropen.app.ui.screens.guide

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunFullGuideChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.utilities.TimeFormatting
import org.hdhropen.kit.viewmodels.GuideViewModel
import kotlin.math.max
import kotlin.math.min

object GuideGridMath {
    const val DP_PER_SECOND = 4.0f / 60.0f // 4dp per minute
    val MIN_CELL_WIDTH = 90.dp
    const val HOUR_SECONDS = 3600.0
    const val DAY_SECONDS = 86400.0

    fun windowBounds(
        nowSeconds: Double,
        fullGuide: List<HDHomeRunFullGuideChannel>
    ): Pair<Double, Double> {
        var minStart = nowSeconds - 2 * HOUR_SECONDS
        var maxEnd = nowSeconds + 4 * HOUR_SECONDS
        val earliestAllowed = nowSeconds - 6 * HOUR_SECONDS

        for (entry in fullGuide) {
            for (airing in entry.airings) {
                airing.start?.let { minStart = min(minStart, it) }
                airing.end?.let { maxEnd = max(maxEnd, it) }
            }
        }

        minStart = max(minStart, earliestAllowed)
        val start = kotlin.math.floor(minStart / 1800.0) * 1800.0
        return Pair(start, maxEnd)
    }

    data class CellLayout(
        val airing: HDHomeRunGuideEntry,
        val leftDp: Dp,
        val widthDp: Dp
    )

    fun cellLayouts(
        airings: List<HDHomeRunGuideEntry>,
        windowStart: Double,
        windowEnd: Double
    ): List<CellLayout> {
        val layouts = mutableListOf<CellLayout>()
        for (airing in airings) {
            val airingStart = airing.start ?: continue
            val airingEnd = airing.end ?: continue
            val start = max(airingStart, windowStart)
            val end = min(airingEnd, windowEnd)
            if (end <= start) continue

            val left = ((start - windowStart) * DP_PER_SECOND).toFloat().dp
            val calculatedWidth = ((end - start) * DP_PER_SECOND).toFloat().dp
            val width = maxOf(calculatedWidth, MIN_CELL_WIDTH)

            layouts.add(CellLayout(airing, left, width))
        }
        return layouts
    }

    data class HourMark(val seconds: Double, val leftDp: Dp, val label: String)
    data class DayMark(val start: Double, val leftDp: Dp, val widthDp: Dp, val label: String)

    fun hourMarks(windowStart: Double, windowEnd: Double): List<HourMark> {
        val marks = mutableListOf<HourMark>()
        var cursor = (kotlin.math.floor(windowStart / 3600.0) * 3600.0)
        while (cursor < windowEnd) {
            if (cursor >= windowStart) {
                val left = ((cursor - windowStart) * DP_PER_SECOND).toFloat().dp
                marks.add(HourMark(cursor, left, TimeFormatting.formatHour(cursor)))
            }
            cursor += 3600.0
        }
        return marks
    }

    fun dayMarks(windowStart: Double, windowEnd: Double): List<DayMark> {
        val marks = mutableListOf<DayMark>()
        var cursor = (kotlin.math.floor(windowStart / 86400.0) * 86400.0)
        while (cursor < windowEnd) {
            val dayEnd = cursor + 86400.0
            val segStart = max(cursor, windowStart)
            val segEnd = min(dayEnd, windowEnd)
            if (segEnd > segStart) {
                val left = ((segStart - windowStart) * DP_PER_SECOND).toFloat().dp
                val width = ((segEnd - segStart) * DP_PER_SECOND).toFloat().dp
                marks.add(DayMark(cursor, left, width, TimeFormatting.formatDayLabel(segStart)))
            }
            cursor = dayEnd
        }
        return marks
    }
}

@Composable
fun GuideGridView(
    channels: List<HDHomeRunChannel>,
    guideViewModel: GuideViewModel,
    onSelectAiring: (HDHomeRunChannel, HDHomeRunGuideEntry) -> Unit,
    onTuneChannel: (HDHomeRunChannel) -> Unit
) {
    val fullGuide by guideViewModel.fullGuide.collectAsState()
    val favoriteChannels by guideViewModel.favoriteChannels.collectAsState()
    val isLoading by guideViewModel.isLoading.collectAsState()
    val density = LocalDensity.current
    var hasAutoScrolledToNow by remember { mutableStateOf(false) }

    var nowSeconds by remember { mutableDoubleStateOf(System.currentTimeMillis() / 1000.0) }

    LaunchedEffect(Unit) {
        while (isActive) {
            delay(30_000)
            nowSeconds = System.currentTimeMillis() / 1000.0
        }
    }

    val (windowStart, windowEnd) = remember(nowSeconds, fullGuide) {
        GuideGridMath.windowBounds(nowSeconds, fullGuide)
    }

    val totalWidth = remember(windowStart, windowEnd) {
        max(((windowEnd - windowStart) * GuideGridMath.DP_PER_SECOND).toFloat(), 100f).dp
    }

    val nowLeft = remember(nowSeconds, windowStart) {
        ((nowSeconds - windowStart) * GuideGridMath.DP_PER_SECOND).toFloat().dp
    }

    val dayMarks = remember(windowStart, windowEnd) { GuideGridMath.dayMarks(windowStart, windowEnd) }
    val hourMarks = remember(windowStart, windowEnd) { GuideGridMath.hourMarks(windowStart, windowEnd) }

    val horizontalScrollState = rememberScrollState()
    val channelColWidth = 92.dp
    val rowHeight = 64.dp
    val rulerHeight = 44.dp

    // One-shot per load: once real guide data has settled, scroll the shared horizontal
    // track (ruler + every channel row) to "now", mirroring the web client's
    // `scrollEl.scrollLeft = nowLeft - 60` (HDHomeRunGuideGrid.svelte). Re-armed whenever a
    // new load starts so returning to the guide after the app has been open a while re-centers.
    LaunchedEffect(isLoading) {
        if (isLoading) {
            hasAutoScrolledToNow = false
        } else if (!hasAutoScrolledToNow && fullGuide.isNotEmpty()) {
            hasAutoScrolledToNow = true
            val targetPx = with(density) { (nowLeft - 60.dp).toPx() }.coerceAtLeast(0f).toInt()
            horizontalScrollState.scrollTo(targetPx)
        }
    }

    Column(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        // Ruler Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(rulerHeight)
                .background(MaterialTheme.colorScheme.surface)
        ) {
            // Pinned corner block above channel column
            Box(
                modifier = Modifier
                    .width(channelColWidth)
                    .fillMaxHeight()
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .border(0.5.dp, MaterialTheme.colorScheme.outline)
            )

            // Horizontally scrolling time marks
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .horizontalScroll(horizontalScrollState)
            ) {
                Box(modifier = Modifier.width(totalWidth).fillMaxHeight()) {
                    // Day marks (top line)
                    for (day in dayMarks) {
                        Text(
                            text = day.label,
                            style = MaterialTheme.typography.labelSmall.copy(
                                color = YellowAccent,
                                fontWeight = FontWeight.Bold
                            ),
                            modifier = Modifier
                                .offset(x = day.leftDp + 6.dp, y = 4.dp)
                        )
                    }

                    // Hour marks (bottom line)
                    for (hour in hourMarks) {
                        Text(
                            text = hour.label,
                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant),
                            modifier = Modifier
                                .offset(x = hour.leftDp + 6.dp, y = 22.dp)
                        )
                    }
                }
            }
        }

        Divider(color = MaterialTheme.colorScheme.outline, thickness = 1.dp)

        // Channels & Airings Grid
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            items(channels, key = { it.channelNumber }) { channel ->
                val isFav = favoriteChannels.contains(channel.channelNumber)
                val airings = guideViewModel.getAirings(channel.channelNumber)
                val layouts = remember(airings, windowStart, windowEnd) {
                    GuideGridMath.cellLayouts(airings, windowStart, windowEnd)
                }

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(rowHeight)
                        .border(0.5.dp, MaterialTheme.colorScheme.outline)
                ) {
                    // Pinned Channel Column Cell
                    Box(
                        modifier = Modifier
                            .width(channelColWidth)
                            .fillMaxHeight()
                            .background(MaterialTheme.colorScheme.surface)
                            .clickable { onTuneChannel(channel) }
                            .padding(horizontal = 8.dp, vertical = 6.dp)
                    ) {
                        Column(verticalArrangement = Arrangement.Center, modifier = Modifier.fillMaxHeight()) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(
                                    text = channel.channelNumber,
                                    style = MaterialTheme.typography.titleMedium.copy(
                                        color = BluePrimary,
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.Bold
                                    )
                                )
                                if (isFav) {
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Icon(
                                        Icons.Default.Star,
                                        contentDescription = "Favorite",
                                        tint = YellowAccent,
                                        modifier = Modifier.size(12.dp)
                                    )
                                }
                                if (channel.isHD) {
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Surface(
                                        color = BluePrimary.copy(alpha = 0.85f),
                                        shape = RoundedCornerShape(3.dp)
                                    ) {
                                        Text(
                                            text = "HD",
                                            style = MaterialTheme.typography.labelSmall.copy(
                                                color = Color.White,
                                                fontSize = 8.sp,
                                                fontWeight = FontWeight.Bold
                                            ),
                                            modifier = Modifier.padding(horizontal = 3.dp, vertical = 1.dp)
                                        )
                                    }
                                }
                            }
                            Text(
                                text = channel.name,
                                style = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant),
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }

                    // Horizontally scrolling airing track
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxHeight()
                            .horizontalScroll(horizontalScrollState)
                            .background(MaterialTheme.colorScheme.background)
                    ) {
                        Box(modifier = Modifier.width(totalWidth).fillMaxHeight()) {
                            // Airing Cells
                            val currentScrollDp = with(density) { horizontalScrollState.value.toFloat().toDp() }
                            for (layout in layouts) {
                                val airing = layout.airing
                                val isLive = airing.isCurrentlyAiring(nowSeconds)
                                val hasRule = guideViewModel.findRule(channel.channelNumber, airing) != null
                                val timeRange = TimeFormatting.formatTimeRange(airing.start, airing.end)

                                // Title/time are offset to follow the visible left edge of the cell as the
                                // row scrolls (like the web client's `position: sticky` cell-title/cell-time,
                                // HDHomeRunGuideGrid.svelte), clamped so they never slide past the cell's own
                                // bounds. Without this, a long-running show whose start has scrolled off-screen
                                // renders as a blank cell -- its title is anchored at the show's start, which
                                // may be hours to the left of the current viewport. Badges are NOT offset, to
                                // match the web client, where they scroll with the cell body.
                                val maxStickyOffset = (layout.widthDp - 96.dp).coerceAtLeast(0.dp)
                                val stickyOffset = (currentScrollDp - layout.leftDp).coerceIn(0.dp, maxStickyOffset)

                                Box(
                                    modifier = Modifier
                                        .offset(x = layout.leftDp)
                                        .width(layout.widthDp)
                                        .fillMaxHeight()
                                        .padding(1.dp)
                                        .clip(RoundedCornerShape(4.dp))
                                        .background(if (isLive) MaterialTheme.colorScheme.surfaceVariant else MaterialTheme.colorScheme.surface)
                                        .border(0.5.dp, if (isLive) BluePrimary.copy(alpha = 0.5f) else MaterialTheme.colorScheme.outline, RoundedCornerShape(4.dp))
                                        .clickable { onSelectAiring(channel, airing) }
                                ) {
                                    if (isLive || hasRule) {
                                        Row(
                                            horizontalArrangement = Arrangement.spacedBy(2.dp),
                                            modifier = Modifier.align(Alignment.TopEnd).padding(6.dp)
                                        ) {
                                            if (isLive) {
                                                Icon(
                                                    Icons.Default.GraphicEq,
                                                    contentDescription = "Live",
                                                    tint = RedLive,
                                                    modifier = Modifier.size(12.dp)
                                                )
                                            }
                                            if (hasRule) {
                                                Icon(
                                                    Icons.Default.FiberManualRecord,
                                                    contentDescription = "Recording Rule",
                                                    tint = RedLive,
                                                    modifier = Modifier.size(12.dp)
                                                )
                                            }
                                        }
                                    }

                                    Column(
                                        modifier = Modifier
                                            .padding(6.dp)
                                            .offset(x = stickyOffset)
                                            .widthIn(max = (layout.widthDp - 12.dp - stickyOffset).coerceAtLeast(40.dp))
                                    ) {
                                        Text(
                                            text = airing.title,
                                            style = MaterialTheme.typography.bodyMedium.copy(
                                                color = MaterialTheme.colorScheme.onSurface,
                                                fontSize = 12.sp,
                                                fontWeight = FontWeight.Bold
                                            ),
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis
                                        )

                                        Spacer(modifier = Modifier.height(2.dp))

                                        Text(
                                            text = timeRange,
                                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.extendedColors.textMuted),
                                            maxLines = 1
                                        )
                                    }
                                }
                            }

                            // Now indicator line
                            if (nowSeconds in windowStart..windowEnd) {
                                Box(
                                    modifier = Modifier
                                        .offset(x = nowLeft)
                                        .width(2.dp)
                                        .fillMaxHeight()
                                        .background(RedLive)
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}
