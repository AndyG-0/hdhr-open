package org.hdhropen.app.ui.screens.guide

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
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
import org.hdhropen.app.ui.screens.ai.AIAssistantBottomSheet
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.hdhropen.kit.viewmodels.RecordingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@UnstableApi
@Composable
fun GuideScreen(
    guideViewModel: GuideViewModel,
    recordingsViewModel: RecordingsViewModel,
    playerViewModel: PlayerViewModel
) {
    val channels by guideViewModel.channels.collectAsState()
    val filterOnlyFavorites by guideViewModel.filterOnlyFavorites.collectAsState()
    val isLoading by guideViewModel.isLoading.collectAsState()
    val dvrInfo by recordingsViewModel.dvrInfo.collectAsState()

    LaunchedEffect(Unit) {
        if (dvrInfo == null) {
            recordingsViewModel.loadDvrInfo()
        }
    }

    var searchQuery by remember { mutableStateOf("") }
    var selectedAiringForSheet by remember { mutableStateOf<Pair<HDHomeRunChannel, HDHomeRunGuideEntry>?>(null) }
    var showAIAssistant by remember { mutableStateOf(false) }

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
                        style = MaterialTheme.typography.titleLarge.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
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
                            tint = if (filterOnlyFavorites) YellowAccent else MaterialTheme.extendedColors.textMuted
                        )
                    }

                    // AI Assistant Button
                    IconButton(onClick = { showAIAssistant = true }) {
                        Icon(
                            Icons.Default.AutoAwesome,
                            contentDescription = "AI Assistant",
                            tint = BluePrimary
                        )
                    }

                    // Refresh Button
                    IconButton(onClick = { guideViewModel.loadData() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh Guide", tint = MaterialTheme.colorScheme.onSurface)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
            )
        },
        containerColor = MaterialTheme.colorScheme.background
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
                placeholder = { Text("Search channels or shows", color = MaterialTheme.extendedColors.textMuted) },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = "Search", tint = MaterialTheme.colorScheme.onSurfaceVariant) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = MaterialTheme.colorScheme.surface,
                    unfocusedContainerColor = MaterialTheme.colorScheme.surface,
                    focusedBorderColor = BluePrimary,
                    unfocusedBorderColor = MaterialTheme.colorScheme.outline,
                    focusedTextColor = MaterialTheme.colorScheme.onSurface,
                    unfocusedTextColor = MaterialTheme.colorScheme.onSurface
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
                channels = channels,
                officialDvrActive = dvrInfo?.isBuiltin == false,
                guideViewModel = guideViewModel,
                onDismiss = { selectedAiringForSheet = null },
                onTune = { playerViewModel.playChannel(channel, airing) }
            )
        }

        if (showAIAssistant) {
            AIAssistantBottomSheet(
                apiClient = guideViewModel.apiClient,
                onDismiss = { showAIAssistant = false }
            )
        }
    }
}
