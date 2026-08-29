package org.hdhropen.app.ui.screens.guide

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.StarOutline
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.media3.common.util.UnstableApi
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.hdhropen.kit.viewmodels.PlayerViewModel

@OptIn(ExperimentalMaterial3Api::class, UnstableApi::class)
@Composable
fun GuideScreen(
    guideViewModel: GuideViewModel,
    playerViewModel: PlayerViewModel
) {
    val channels by guideViewModel.channels.collectAsState()
    val filterOnlyFavorites by guideViewModel.filterOnlyFavorites.collectAsState()
    val isLoading by guideViewModel.isLoading.collectAsState()

    var searchQuery by remember { mutableStateOf("") }
    var selectedAiringForSheet by remember { mutableStateOf<Pair<HDHomeRunChannel, HDHomeRunGuideEntry>?>(null) }

    LaunchedEffect(Unit) {
        if (channels.isEmpty()) {
            guideViewModel.loadData()
        }
    }

    val displayedChannels = remember(channels, filterOnlyFavorites, searchQuery) {
        val base = guideViewModel.displayedChannels
        if (searchQuery.isEmpty()) {
            base
        } else {
            base.filter {
                it.name.contains(searchQuery, ignoreCase = true) ||
                        it.channelNumber.contains(searchQuery) ||
                        (it.now?.title?.contains(searchQuery, ignoreCase = true) == true)
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Live Guide",
                        style = MaterialTheme.typography.titleLarge.copy(color = TextPrimary, fontWeight = FontWeight.Bold)
                    )
                },
                actions = {
                    // Favorites Toggle Filter
                    IconButton(onClick = {
                        guideViewModel.filterOnlyFavorites.value = !filterOnlyFavorites
                    }) {
                        Icon(
                            if (filterOnlyFavorites) Icons.Default.Star else Icons.Default.StarOutline,
                            contentDescription = "Filter Favorites",
                            tint = if (filterOnlyFavorites) YellowAccent else TextMuted
                        )
                    }

                    // Refresh Button
                    IconButton(onClick = { guideViewModel.loadData() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh Guide", tint = TextPrimary)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = DarkSurface)
            )
        },
        containerColor = DarkBackground
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Search Box
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                placeholder = { Text("Search channels or shows", color = TextMuted) },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = "Search", tint = TextSecondary) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = DarkSurface,
                    unfocusedContainerColor = DarkSurface,
                    focusedBorderColor = BluePrimary,
                    unfocusedBorderColor = DarkBorder,
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary
                ),
                singleLine = true
            )

            if (isLoading && channels.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = BluePrimary)
                }
            } else {
                GuideGridView(
                    channels = displayedChannels,
                    guideViewModel = guideViewModel,
                    onSelectAiring = { channel, airing ->
                        selectedAiringForSheet = Pair(channel, airing)
                    },
                    onTuneChannel = { channel ->
                        playerViewModel.playChannel(channel)
                    }
                )
            }
        }

        selectedAiringForSheet?.let { (channel, airing) ->
            ProgramDetailBottomSheet(
                channel = channel,
                airing = airing,
                guideViewModel = guideViewModel,
                onDismiss = { selectedAiringForSheet = null },
                onTune = { playerViewModel.playChannel(channel, airing) }
            )
        }
    }
}
