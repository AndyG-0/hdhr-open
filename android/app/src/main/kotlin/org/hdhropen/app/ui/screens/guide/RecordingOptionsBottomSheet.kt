package org.hdhropen.app.ui.screens.guide

import androidx.compose.foundation.clickable
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
import org.hdhropen.app.ui.theme.RedLive
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import org.hdhropen.kit.models.RecordingRuleOptions

// Mirrors the web client's HDHomeRunRecordingOptionsDialog.svelte: keyword
// query or "contains" title matching forces the rule onto the builtin DVR
// server (enforced again server-side by dvr.py), and per-episode retention
// is meaningless (and hidden) once the rule targets the official HDHomeRun
// RECORD engine, which manages its own retention.
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecordingOptionsBottomSheet(
    channel: HDHomeRunChannel,
    airing: HDHomeRunGuideEntry,
    channels: List<HDHomeRunChannel>,
    canRecordSeries: Boolean,
    officialDvrActive: Boolean,
    existingRule: HDHomeRunRecordingRule?,
    onConfirm: (isSeries: Boolean, options: RecordingRuleOptions) -> Unit,
    onCancelRule: (() -> Unit)?,
    onDismiss: () -> Unit
) {
    val chOnly = existingRule?.channelOnly
    val maxKeep = existingRule?.maxEpisodesToKeep

    var server by remember {
        mutableStateOf(
            if (existingRule?.provider == "hdhomerun") "hdhomerun"
            else if (existingRule?.provider == "builtin") "builtin"
            else "default"
        )
    }
    var titleMatchMode by remember { mutableStateOf(existingRule?.titleMatchMode ?: "exact") }
    var keywordQuery by remember { mutableStateOf(existingRule?.keywordQuery ?: "") }
    var channelMode by remember {
        mutableStateOf(
            if (chOnly != null) {
                if (chOnly.contains("|")) "custom"
                else if (chOnly == channel.channelNumber) "current"
                else "custom"
            } else if (existingRule != null) {
                "any"
            } else {
                "current"
            }
        )
    }
    var customChannels by remember {
        mutableStateOf(
            if (chOnly != null) {
                chOnly.split("|").filter { it.isNotBlank() }.toSet()
            } else {
                setOf(channel.channelNumber)
            }
        )
    }
    var startPaddingMinutes by remember { mutableStateOf(((existingRule?.startPadding ?: 0) / 60).toString()) }
    var endPaddingMinutes by remember { mutableStateOf(((existingRule?.endPadding ?: 0) / 60).toString()) }
    var recentOnly by remember { mutableStateOf((existingRule?.recentOnly ?: 0) != 0) }
    var retentionMode by remember {
        mutableStateOf(
            if (maxKeep != null && maxKeep > 0) "limited"
            else "unlimited"
        )
    }
    var retentionCount by remember { mutableStateOf((maxKeep ?: 3).toString()) }

    val isKeywordActive = keywordQuery.trim().isNotEmpty() || titleMatchMode == "contains"
    val isOfficialDvrTarget = !isKeywordActive && (server == "hdhomerun" || (server == "default" && officialDvrActive))

    fun effectiveChannel(): String? = when (channelMode) {
        "any" -> null
        "current" -> channel.channelNumber
        "custom" -> customChannels.filter { it.isNotBlank() }.takeIf { it.isNotEmpty() }?.joinToString("|")
        else -> null
    }

    fun buildOptions(): RecordingRuleOptions {
        val trimmedKeyword = keywordQuery.trim()
        val hasKeywords = trimmedKeyword.isNotEmpty()
        val hasContains = titleMatchMode == "contains"
        val serverToUse = if (hasKeywords || hasContains) "builtin" else if (server != "default") server else null
        return RecordingRuleOptions(
            title = airing.title,
            titleMatchMode = if (hasContains) "contains" else "exact",
            keywordQuery = if (hasKeywords) trimmedKeyword else null,
            channel = effectiveChannel(),
            startPadding = startPaddingMinutes.toIntOrNull()?.takeIf { it != 0 }?.times(60),
            endPadding = endPaddingMinutes.toIntOrNull()?.takeIf { it != 0 }?.times(60),
            recentOnly = if (recentOnly) true else null,
            maxEpisodesToKeep = if (!isOfficialDvrTarget && retentionMode == "limited") {
                retentionCount.toIntOrNull()?.takeIf { it > 0 }
            } else null,
            server = serverToUse
        )
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 12.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text(
                text = "Recording Options",
                style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
            )
            Spacer(Modifier.height(2.dp))
            Text(
                text = airing.title,
                style = MaterialTheme.typography.bodyMedium.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
            )

            Spacer(Modifier.height(16.dp))

            RadioGroupField(
                label = "DVR Server",
                options = listOf("default" to "Default", "builtin" to "Built-in DVR", "hdhomerun" to "HDHomeRun RECORD"),
                selected = server,
                onSelect = { server = it }
            )

            Spacer(Modifier.height(12.dp))

            RadioGroupField(
                label = "Title Match",
                options = listOf("exact" to "Exact title", "contains" to "Title contains"),
                selected = titleMatchMode,
                onSelect = { titleMatchMode = it }
            )

            Spacer(Modifier.height(12.dp))

            OutlinedTextField(
                value = keywordQuery,
                onValueChange = { keywordQuery = it },
                label = { Text("Keywords (optional)") },
                placeholder = { Text("e.g. Ohio State, Michigan") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true
            )
            if (!airing.episodeTitle.isNullOrEmpty() && !keywordQuery.lowercase().contains(airing.episodeTitle!!.lowercase())) {
                TextButton(onClick = {
                    keywordQuery = if (keywordQuery.isBlank()) airing.episodeTitle!! else "${keywordQuery.trim()}, ${airing.episodeTitle}"
                }) {
                    Text("+ Use \"${airing.episodeTitle}\" as keyword")
                }
            }
            if (isKeywordActive) {
                Text(
                    text = "Keyword and contains-match rules always record via the built-in DVR.",
                    style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant),
                    modifier = Modifier.padding(top = 4.dp)
                )
            }

            Spacer(Modifier.height(12.dp))

            val channelOptions = buildList {
                add("current" to "Channel ${channel.channelNumber} ${channel.name}".trim())
                add("any" to "Any channel")
                if (channels.isNotEmpty()) add("custom" to "Select channels…")
            }
            RadioGroupField(label = "Channel", options = channelOptions, selected = channelMode, onSelect = { channelMode = it })

            if (channelMode == "custom" && channels.isNotEmpty()) {
                Column(modifier = Modifier.fillMaxWidth().heightIn(max = 220.dp).verticalScroll(rememberScrollState())) {
                    channels.forEach { ch ->
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth()
                        ) {
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

            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { recentOnly = !recentOnly }
            ) {
                Checkbox(checked = recentOnly, onCheckedChange = { recentOnly = it })
                Text("New episodes only", style = MaterialTheme.typography.bodyMedium)
            }

            Spacer(Modifier.height(8.dp))

            if (isOfficialDvrTarget) {
                Text(
                    text = "Retention is managed by the official HDHomeRun DVR.",
                    style = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                )
            } else {
                RadioGroupField(
                    label = "Keep episodes",
                    options = listOf("unlimited" to "Unlimited", "limited" to "Keep last N"),
                    selected = retentionMode,
                    onSelect = { retentionMode = it }
                )
                if (retentionMode == "limited") {
                    OutlinedTextField(
                        value = retentionCount,
                        onValueChange = { retentionCount = it.filter(Char::isDigit) },
                        label = { Text("Episodes to keep") },
                        modifier = Modifier.width(140.dp),
                        singleLine = true
                    )
                }
            }

            Spacer(Modifier.height(20.dp))

            if (existingRule != null) {
                Button(
                    onClick = { onConfirm(existingRule.isSeriesRule, buildOptions()); onDismiss() },
                    modifier = Modifier.fillMaxWidth().height(48.dp)
                ) {
                    Text(if (existingRule.isSeriesRule) "Update Series Recording" else "Update Episode Recording")
                }
                if (onCancelRule != null) {
                    Spacer(Modifier.height(10.dp))
                    OutlinedButton(
                        onClick = { onCancelRule(); onDismiss() },
                        modifier = Modifier.fillMaxWidth().height(48.dp),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = RedLive)
                    ) {
                        Text("Cancel Recording")
                    }
                }
            } else {
                Button(
                    onClick = { onConfirm(false, buildOptions()); onDismiss() },
                    modifier = Modifier.fillMaxWidth().height(48.dp)
                ) {
                    Text("Record Episode")
                }
                if (canRecordSeries) {
                    Spacer(Modifier.height(10.dp))
                    Button(
                        onClick = { onConfirm(true, buildOptions()); onDismiss() },
                        modifier = Modifier.fillMaxWidth().height(48.dp)
                    ) {
                        Text(if (isKeywordActive) "Record Series (with keywords)" else "Record Series")
                    }
                }
            }

            Spacer(Modifier.height(16.dp))
        }
    }
}

@Composable
private fun RadioGroupField(
    label: String,
    options: List<Pair<String, String>>,
    selected: String,
    onSelect: (String) -> Unit
) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(label, style = MaterialTheme.typography.labelLarge.copy(color = MaterialTheme.colorScheme.onSurface))
        options.forEach { (value, text) ->
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onSelect(value) }
            ) {
                RadioButton(selected = selected == value, onClick = { onSelect(value) })
                Text(text, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}
