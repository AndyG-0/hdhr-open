package org.hdhropen.app.ui.screens.discovery

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.screens.guide.RecordingOptionsBottomSheet
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.viewmodels.DiscoveryViewModel
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.hdhropen.kit.viewmodels.RecordingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DiscoveryScreen(
    discoveryViewModel: DiscoveryViewModel,
    guideViewModel: GuideViewModel,
    recordingsViewModel: RecordingsViewModel
) {
    val items by discoveryViewModel.items.collectAsStateWithLifecycle()
    val hasProfile by discoveryViewModel.hasProfile.collectAsStateWithLifecycle()
    val isLoading by discoveryViewModel.isLoading.collectAsStateWithLifecycle()
    val channels by guideViewModel.channels.collectAsStateWithLifecycle()
    val dvrInfo by recordingsViewModel.dvrInfo.collectAsStateWithLifecycle()
    val coroutineScope = rememberCoroutineScope()

    var selectedItemForSheet by remember { mutableStateOf<HDHomeRunGuideEntry?>(null) }

    LaunchedEffect(Unit) {
        if (items.isEmpty()) {
            discoveryViewModel.loadData()
        }
        if (channels.isEmpty()) {
            guideViewModel.loadChannels()
        }
        if (dvrInfo == null) {
            recordingsViewModel.loadDvrInfo()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Discovery",
                        style = MaterialTheme.typography.titleLarge.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
                    )
                },
                actions = {
                    IconButton(onClick = { discoveryViewModel.loadData() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = MaterialTheme.colorScheme.onSurface)
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
            // Cold-start banner: shown when recommendations aren't personalized
            // yet (no recording history), mirroring the web client's header.
            if (!hasProfile && items.isNotEmpty()) {
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                ) {
                    Text(
                        text = "New & Notable — record a few shows to get picks tailored to you",
                        style = MaterialTheme.typography.bodySmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant),
                        modifier = Modifier.padding(12.dp)
                    )
                }
            }

            if (isLoading && items.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = BluePrimary)
                }
            } else if (items.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No recommendations yet.", color = MaterialTheme.extendedColors.textMuted)
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = PaddingValues(vertical = 8.dp)
                ) {
                    items(items, key = { it.id }) { entry ->
                        val channel = channels.firstOrNull { it.channelNumber == entry.channelNumber }
                        DiscoveryCard(
                            item = entry,
                            channel = channel,
                            onClick = { selectedItemForSheet = entry }
                        )
                    }
                }
            }
        }

        selectedItemForSheet?.let { entry ->
            // Discovery candidates are guaranteed by the backend to never
            // have an existing recording rule, so existingRule/onCancelRule
            // are always absent here - same wiring as ProgramDetailBottomSheet
            // minus its update-existing-rule branch.
            val channel = channels.firstOrNull { it.channelNumber == entry.channelNumber }
                ?: HDHomeRunChannel(channelNumber = entry.channelNumber ?: "", name = "")
            RecordingOptionsBottomSheet(
                channel = channel,
                airing = entry,
                channels = channels,
                canRecordSeries = true,
                officialDvrActive = dvrInfo?.isBuiltin == false,
                existingRule = null,
                onConfirm = { isSeries, options ->
                    coroutineScope.launch {
                        if (isSeries) {
                            guideViewModel.recordSeries(
                                seriesId = entry.seriesId ?: "",
                                channelNumber = channel.channelNumber,
                                options = options
                            )
                        } else {
                            guideViewModel.recordEpisode(
                                seriesId = entry.seriesId,
                                channelNumber = channel.channelNumber,
                                start = entry.start,
                                options = options
                            )
                        }
                    }
                },
                onCancelRule = null,
                onDismiss = { selectedItemForSheet = null }
            )
        }
    }
}
