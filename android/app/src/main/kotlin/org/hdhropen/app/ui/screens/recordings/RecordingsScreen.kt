package org.hdhropen.app.ui.screens.recordings

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.media3.common.util.UnstableApi
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.hdhropen.kit.viewmodels.RecordingCategoryFilter
import org.hdhropen.kit.viewmodels.RecordingsViewModel

@OptIn(ExperimentalMaterial3Api::class, UnstableApi::class)
@Composable
fun RecordingsScreen(
    recordingsViewModel: RecordingsViewModel,
    playerViewModel: PlayerViewModel
) {
    val recordings by recordingsViewModel.recordings.collectAsState()
    val recordingRules by recordingsViewModel.recordingRules.collectAsState()
    val dvrInfo by recordingsViewModel.dvrInfo.collectAsState()
    val selectedFilter by recordingsViewModel.selectedFilter.collectAsState()
    val isLoading by recordingsViewModel.isLoading.collectAsState()

    var selectedRecordingForSheet by remember { mutableStateOf<HDHomeRunRecording?>(null) }
    var showRulesDialog by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        if (recordings.isEmpty()) {
            recordingsViewModel.loadData()
        }
    }

    val filteredList = remember(recordings, selectedFilter) {
        recordingsViewModel.filteredRecordings
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Recordings",
                        style = MaterialTheme.typography.titleLarge.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
                    )
                },
                actions = {
                    // Scheduled Rules Button
                    IconButton(onClick = { showRulesDialog = true }) {
                        Icon(Icons.Default.List, contentDescription = "Rules", tint = MaterialTheme.colorScheme.onSurface)
                    }

                    // Refresh Button
                    IconButton(onClick = { recordingsViewModel.loadData() }) {
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
            // Storage Meter Header (if available)
            dvrInfo?.let { info ->
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = info.friendlyName.ifEmpty { "HDHomeRun DVR" },
                                style = MaterialTheme.typography.titleMedium.copy(
                                    color = MaterialTheme.colorScheme.onSurface,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Bold
                                )
                            )
                            Text(
                                text = "${recordings.size} total recordings",
                                style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                            )
                        }

                        Text(
                            text = info.formattedFreeSpace,
                            style = MaterialTheme.typography.labelMedium.copy(
                                color = YellowAccent,
                                fontWeight = FontWeight.Bold
                            )
                        )
                    }
                }
            }

            // Category Filter Chips
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                RecordingCategoryFilter.values().forEach { filter ->
                    FilterChip(
                        selected = selectedFilter == filter,
                        onClick = { recordingsViewModel.selectedFilter.value = filter },
                        label = {
                            Text(
                                text = filter.label,
                                style = MaterialTheme.typography.labelMedium.copy(
                                    color = if (selectedFilter == filter) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            )
                        },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = BluePrimary,
                            containerColor = MaterialTheme.colorScheme.surface
                        ),
                        border = FilterChipDefaults.filterChipBorder(
                            borderColor = MaterialTheme.colorScheme.outline,
                            selectedBorderColor = BluePrimary,
                            enabled = true,
                            selected = selectedFilter == filter
                        )
                    )
                }
            }

            // Recordings List
            if (isLoading && recordings.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = BluePrimary)
                }
            } else if (filteredList.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No recordings found.", color = MaterialTheme.extendedColors.textMuted)
                }
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    contentPadding = PaddingValues(vertical = 8.dp)
                ) {
                    items(filteredList, key = { it.id }) { recording ->
                        RecordingCard(
                            recording = recording,
                            onClick = { selectedRecordingForSheet = recording }
                        )
                    }
                }
            }
        }

        selectedRecordingForSheet?.let { recording ->
            RecordingDetailBottomSheet(
                recording = recording,
                recordingsViewModel = recordingsViewModel,
                onDismiss = { selectedRecordingForSheet = null },
                onPlay = { playerViewModel.playRecording(recording) }
            )
        }

        if (showRulesDialog) {
            RecordingRulesDialog(
                rules = recordingRules,
                recordingsViewModel = recordingsViewModel,
                onDismiss = { showRulesDialog = false }
            )
        }
    }
}
