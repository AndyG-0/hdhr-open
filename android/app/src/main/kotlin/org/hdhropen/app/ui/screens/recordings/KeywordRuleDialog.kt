package org.hdhropen.app.ui.screens.recordings

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.RecordingRuleOptions

// Mirrors the web client's HDHomeRunKeywordRuleDialog.svelte — creates a
// standalone standing rule (no backing airing). Always a builtin-DVR rule,
// enforced both here and server-side (see RecordingsViewModel.createKeywordRule).
@Composable
fun KeywordRuleDialog(
    channels: List<HDHomeRunChannel>,
    loading: Boolean,
    onConfirm: (title: String, options: RecordingRuleOptions) -> Unit,
    onDismiss: () -> Unit
) {
    var title by remember { mutableStateOf("") }
    var titleMatchMode by remember { mutableStateOf("exact") }
    var keywordQuery by remember { mutableStateOf("") }
    var channelMode by remember { mutableStateOf("any") }
    var customChannels by remember { mutableStateOf(setOf<String>()) }
    var startPaddingMinutes by remember { mutableStateOf("0") }
    var endPaddingMinutes by remember { mutableStateOf("0") }
    var recentOnly by remember { mutableStateOf(false) }
    var retentionMode by remember { mutableStateOf("unlimited") }
    var retentionCount by remember { mutableStateOf("3") }

    val canSubmit = title.trim().isNotEmpty()

    fun effectiveChannel(): String? = when (channelMode) {
        "custom" -> customChannels.filter { it.isNotBlank() }.takeIf { it.isNotEmpty() }?.joinToString("|")
        else -> null
    }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxWidth().fillMaxHeight(0.85f).padding(16.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .verticalScroll(rememberScrollState())
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Add Keyword Rule",
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
                    )
                }

                Spacer(Modifier.height(12.dp))

                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Title") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                Spacer(Modifier.height(12.dp))

                Column {
                    Text("Title Match", style = MaterialTheme.typography.labelLarge)
                    listOf("exact" to "Exact title", "contains" to "Title contains").forEach { (value, label) ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = titleMatchMode == value, onClick = { titleMatchMode = value })
                            Text(label, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }

                Spacer(Modifier.height(12.dp))

                OutlinedTextField(
                    value = keywordQuery,
                    onValueChange = { keywordQuery = it },
                    label = { Text("Keywords (optional)") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )

                if (channels.isNotEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Column {
                        Text("Channel", style = MaterialTheme.typography.labelLarge)
                        listOf("any" to "Any channel", "custom" to "Select channels…").forEach { (value, label) ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                RadioButton(selected = channelMode == value, onClick = { channelMode = value })
                                Text(label, style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                    }
                    if (channelMode == "custom") {
                        Column(modifier = Modifier.fillMaxWidth().heightIn(max = 180.dp).verticalScroll(rememberScrollState())) {
                            channels.forEach { ch ->
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Checkbox(
                                        checked = customChannels.contains(ch.channelNumber),
                                        onCheckedChange = { checked ->
                                            customChannels = if (checked) customChannels + ch.channelNumber else customChannels - ch.channelNumber
                                        }
                                    )
                                    Text("${ch.channelNumber} ${ch.name}", style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                    }
                }

                Spacer(Modifier.height(12.dp))

                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedTextField(
                        value = startPaddingMinutes,
                        onValueChange = { startPaddingMinutes = it.filter(Char::isDigit) },
                        label = { Text("Start padding (min)") },
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                    OutlinedTextField(
                        value = endPaddingMinutes,
                        onValueChange = { endPaddingMinutes = it.filter(Char::isDigit) },
                        label = { Text("End padding (min)") },
                        modifier = Modifier.weight(1f),
                        singleLine = true
                    )
                }

                Spacer(Modifier.height(8.dp))

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = recentOnly, onCheckedChange = { recentOnly = it })
                    Text("New episodes only", style = MaterialTheme.typography.bodyMedium)
                }

                Spacer(Modifier.height(8.dp))

                Column {
                    Text("Keep episodes", style = MaterialTheme.typography.labelLarge)
                    listOf("unlimited" to "Unlimited", "limited" to "Keep last N").forEach { (value, label) ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = retentionMode == value, onClick = { retentionMode = value })
                            Text(label, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
                if (retentionMode == "limited") {
                    OutlinedTextField(
                        value = retentionCount,
                        onValueChange = { retentionCount = it.filter(Char::isDigit) },
                        label = { Text("Episodes to keep") },
                        modifier = Modifier.width(140.dp),
                        singleLine = true
                    )
                }

                Spacer(Modifier.height(20.dp))

                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = onDismiss) { Text("Cancel") }
                    Spacer(Modifier.width(8.dp))
                    Button(
                        enabled = canSubmit && !loading,
                        onClick = {
                            val options = RecordingRuleOptions(
                                titleMatchMode = titleMatchMode,
                                keywordQuery = keywordQuery.trim().takeIf { it.isNotEmpty() },
                                channel = effectiveChannel(),
                                startPadding = startPaddingMinutes.toIntOrNull()?.takeIf { it != 0 }?.times(60),
                                endPadding = endPaddingMinutes.toIntOrNull()?.takeIf { it != 0 }?.times(60),
                                recentOnly = if (recentOnly) true else null,
                                maxEpisodesToKeep = if (retentionMode == "limited") {
                                    retentionCount.toIntOrNull()?.takeIf { it > 0 }
                                } else null
                            )
                            onConfirm(title.trim(), options)
                        }
                    ) {
                        Text("Create Rule")
                    }
                }
            }
        }
    }
}
