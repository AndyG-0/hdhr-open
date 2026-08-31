package org.hdhropen.app.ui.screens.tuners

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.SettingsInputAntenna
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunTuner
import org.hdhropen.kit.viewmodels.TunerViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TunerStatusScreen(
    tunerViewModel: TunerViewModel
) {
    val tuners by tunerViewModel.tuners.collectAsState()
    val tunerInfo by tunerViewModel.tunerInfo.collectAsState()
    val isLoading by tunerViewModel.isLoading.collectAsState()

    DisposableEffect(Unit) {
        tunerViewModel.loadData()
        tunerViewModel.startPolling(3000)
        onDispose {
            tunerViewModel.stopPolling()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = "Tuners",
                        style = MaterialTheme.typography.titleLarge.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
                    )
                },
                actions = {
                    IconButton(onClick = { tunerViewModel.loadData() }) {
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
                .padding(horizontal = 16.dp)
        ) {
            Spacer(modifier = Modifier.height(8.dp))

            // Device Info Card
            tunerInfo?.let { info ->
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    modifier = Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.SettingsInputAntenna, contentDescription = "Device", tint = BluePrimary)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = info.friendlyName.ifEmpty { "HDHomeRun Tuner" },
                                style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
                            )
                        }

                        Spacer(modifier = Modifier.height(8.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            info.modelNumber?.let {
                                Text(text = "Model: $it", style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant))
                            }
                            info.firmwareVersion?.let {
                                Text(text = "Firmware: $it", style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant))
                            }
                            info.tunerCount?.let {
                                Text(text = "$it Tuners", style = MaterialTheme.typography.labelSmall.copy(color = YellowAccent))
                            }
                        }
                    }
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            // Tuners List
            if (isLoading && tuners.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = BluePrimary)
                }
            } else if (tuners.isEmpty()) {
                Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No HDHomeRun tuners found.", color = MaterialTheme.extendedColors.textMuted)
                }
            } else {
                LazyColumn(
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.fillMaxSize()
                ) {
                    items(tuners, key = { it.id }) { tuner ->
                        TunerCard(tuner = tuner)
                    }
                }
            }
        }
    }
}

@Composable
private fun TunerCard(tuner: HDHomeRunTuner) {
    Card(
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, MaterialTheme.colorScheme.outline, RoundedCornerShape(12.dp))
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Tuner ${tuner.index}",
                    style = MaterialTheme.typography.titleMedium.copy(
                        color = MaterialTheme.colorScheme.onSurface,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                )

                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .background(if (tuner.inUse) GreenActive.copy(alpha = 0.2f) else MaterialTheme.colorScheme.surfaceVariant)
                        .border(1.dp, if (tuner.inUse) GreenActive else MaterialTheme.colorScheme.outline, RoundedCornerShape(6.dp))
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                ) {
                    Text(
                        text = if (tuner.inUse) "IN USE" else "IDLE",
                        style = MaterialTheme.typography.labelSmall.copy(
                            color = if (tuner.inUse) GreenActive else MaterialTheme.extendedColors.textMuted,
                            fontWeight = FontWeight.Bold
                        )
                    )
                }
            }

            if (tuner.inUse) {
                Spacer(modifier = Modifier.height(10.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "Channel: ${tuner.channelNumber ?: ""} ${tuner.channelName ?: ""}",
                        style = MaterialTheme.typography.bodyMedium.copy(color = YellowAccent, fontWeight = FontWeight.SemiBold)
                    )
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Metric: Signal Strength
                tuner.signalStrengthPercent?.let { pct ->
                    MetricProgressBar(label = "Signal Strength", percent = pct)
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Metric: Signal Quality
                tuner.signalQualityPercent?.let { pct ->
                    MetricProgressBar(label = "Signal Quality (SNR)", percent = pct)
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Metric: Symbol Quality
                tuner.symbolQualityPercent?.let { pct ->
                    MetricProgressBar(label = "Symbol Quality", percent = pct)
                    Spacer(modifier = Modifier.height(8.dp))
                }

                // Network Bitrate
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(text = "Data Rate", style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant))
                    Text(
                        text = tuner.formattedRateMbps,
                        style = MaterialTheme.typography.labelSmall.copy(color = BluePrimary, fontWeight = FontWeight.Bold)
                    )
                }
            }
        }
    }
}

@Composable
private fun MetricProgressBar(label: String, percent: Int) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(text = label, style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant))
            Text(
                text = "$percent%",
                style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
            )
        }
        Spacer(modifier = Modifier.height(4.dp))
        LinearProgressIndicator(
            progress = { (percent / 100f).coerceIn(0f, 1f) },
            color = when {
                percent >= 80 -> GreenActive
                percent >= 50 -> YellowAccent
                else -> RedLive
            },
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp))
        )
    }
}
