package org.hdhropen.app.ui.screens.recordings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import org.hdhropen.kit.viewmodels.RecordingsViewModel

@Composable
private fun RuleBadgesRow(rule: HDHomeRunRecordingRule) {
    val badges = buildList {
        if (!rule.keywordQuery.isNullOrEmpty()) add("Keyword: ${rule.keywordQuery}")
        if (rule.titleMatchMode == "contains") add("Contains match")
        if (rule.recentOnly == 1) add("New only")
        rule.maxEpisodesToKeep?.let { add("Keep last $it") }
        rule.startPadding?.takeIf { it != 0 }?.let { add("Start +${it / 60}m") }
        rule.endPadding?.takeIf { it != 0 }?.let { add("End +${it / 60}m") }
        rule.provider?.let { add(it) }
    }
    if (badges.isEmpty()) return
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        badges.take(4).forEach { badge ->
            Surface(
                color = MaterialTheme.colorScheme.surface,
                shape = RoundedCornerShape(3.dp)
            ) {
                Text(
                    text = badge,
                    style = MaterialTheme.typography.labelSmall.copy(
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontSize = 9.sp
                    ),
                    modifier = Modifier.padding(horizontal = 4.dp, vertical = 1.dp)
                )
            }
        }
    }
}

@Composable
fun RecordingRulesDialog(
    rules: List<HDHomeRunRecordingRule>,
    recordingsViewModel: RecordingsViewModel,
    onDismiss: () -> Unit
) {
    val coroutineScope = rememberCoroutineScope()

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxWidth().fillMaxHeight(0.7f).padding(16.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Scheduled Rules",
                        style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Bold)
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                if (rules.isEmpty()) {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("No scheduled rules.", color = MaterialTheme.extendedColors.textMuted)
                    }
                } else {
                    LazyColumn(
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                        modifier = Modifier.fillMaxSize()
                    ) {
                        items(rules, key = { it.recordingRuleId }) { rule ->
                            Card(
                                shape = RoundedCornerShape(10.dp),
                                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Row(
                                    modifier = Modifier.padding(12.dp).fillMaxWidth(),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = rule.title,
                                            style = MaterialTheme.typography.titleMedium.copy(
                                                color = MaterialTheme.colorScheme.onSurface,
                                                fontSize = 14.sp,
                                                fontWeight = FontWeight.Bold
                                            )
                                        )
                                        Spacer(modifier = Modifier.height(2.dp))
                                        val type = if (rule.isSeriesRule) "Series Rule" else "Single Episode"
                                        val ch = rule.channelOnly?.let { " • Ch $it" } ?: ""
                                        Text(
                                            text = "$type$ch",
                                            style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                                        )
                                        Spacer(modifier = Modifier.height(4.dp))
                                        RuleBadgesRow(rule)
                                    }

                                    IconButton(onClick = {
                                        coroutineScope.launch {
                                            recordingsViewModel.deleteRule(rule.recordingRuleId)
                                            recordingsViewModel.loadRules()
                                        }
                                    }) {
                                        Icon(Icons.Default.Delete, contentDescription = "Delete Rule", tint = RedLive)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
