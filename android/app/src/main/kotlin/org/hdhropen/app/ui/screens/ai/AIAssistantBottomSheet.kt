package org.hdhropen.app.ui.screens.ai

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.serialization.json.JsonPrimitive
import org.hdhropen.app.ui.theme.BluePrimary
import org.hdhropen.app.ui.theme.RedLive
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.AIAssistantViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AIAssistantBottomSheet(
    apiClient: APIClient,
    onDismiss: () -> Unit
) {
    val viewModel = remember(apiClient) { AIAssistantViewModel(apiClient) }
    AIAssistantBottomSheet(
        viewModel = viewModel,
        onDismiss = onDismiss
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AIAssistantBottomSheet(
    viewModel: AIAssistantViewModel,
    onDismiss: () -> Unit
) {
    val turns by viewModel.turns.collectAsState()
    val isSending by viewModel.isSending.collectAsState()
    val errorText by viewModel.errorText.collectAsState()
    var inputText by remember { mutableStateOf("") }
    val listState = rememberLazyListState()

    LaunchedEffect(turns.size, turns.lastOrNull()?.text) {
        if (turns.isNotEmpty()) {
            listState.animateScrollToItem(turns.size - 1)
        }
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = MaterialTheme.colorScheme.surface,
        scrimColor = MaterialTheme.colorScheme.background.copy(alpha = 0.6f),
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .fillMaxHeight(0.88f)
                .padding(bottom = 16.dp)
        ) {
            // Header
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Default.AutoAwesome,
                        contentDescription = null,
                        tint = BluePrimary,
                        modifier = Modifier.size(24.dp)
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "AI Assistant",
                        style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold)
                    )
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (turns.isNotEmpty()) {
                        TextButton(
                            onClick = { viewModel.newChat() },
                            enabled = !isSending
                        ) {
                            Text("New Chat")
                        }
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Default.Close, contentDescription = "Close")
                    }
                }
            }

            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

            // Chat Feed
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
                contentPadding = PaddingValues(vertical = 12.dp)
            ) {
                if (turns.isEmpty()) {
                    item {
                        EmptyStateView(onSelectSuggestion = {
                            viewModel.sendPrompt(it)
                        })
                    }
                } else {
                    items(turns, key = { it.id }) { turn ->
                        ChatTurnView(
                            turn = turn,
                            onConfirmAction = { actionId ->
                                viewModel.confirmAction(actionId)
                            },
                            onCancelAction = { actionId ->
                                viewModel.cancelAction(actionId)
                            }
                        )
                    }

                    if (isSending && (turns.lastOrNull()?.text.isNullOrEmpty()) && (turns.lastOrNull()?.toolStatuses?.isEmpty() == true)) {
                        item {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                modifier = Modifier.padding(start = 8.dp)
                            ) {
                                CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    "Thinking...",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }
            }

            errorText?.let { err ->
                Text(
                    text = err,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f))
                        .padding(horizontal = 16.dp, vertical = 6.dp)
                )
            }

            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

            // Input Row
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = inputText,
                    onValueChange = { inputText = it },
                    placeholder = { Text("Ask about schedules, sports, or DVR...") },
                    modifier = Modifier.weight(1f),
                    maxLines = 3,
                    shape = RoundedCornerShape(24.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedContainerColor = MaterialTheme.colorScheme.surfaceVariant,
                        unfocusedContainerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                )

                Spacer(Modifier.width(8.dp))

                IconButton(
                    onClick = {
                        val prompt = inputText
                        inputText = ""
                        viewModel.sendPrompt(prompt)
                    },
                    enabled = inputText.isNotBlank() && !isSending,
                    modifier = Modifier
                        .size(44.dp)
                        .background(
                            if (inputText.isNotBlank() && !isSending) BluePrimary else MaterialTheme.colorScheme.surfaceVariant,
                            CircleShape
                        )
                ) {
                    Icon(
                        Icons.Default.ArrowUpward,
                        contentDescription = "Send",
                        tint = if (inputText.isNotBlank() && !isSending) Color.White else MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
private fun EmptyStateView(onSelectSuggestion: (String) -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 24.dp, horizontal = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            Icons.Default.AutoAwesome,
            contentDescription = null,
            tint = BluePrimary,
            modifier = Modifier.size(48.dp)
        )
        Spacer(Modifier.height(12.dp))
        Text(
            "What can I help you find?",
            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold)
        )
        Spacer(Modifier.height(4.dp))
        Text(
            "Ask about live programs, upcoming sports, or manage your DVR recordings.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(Modifier.height(20.dp))

        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            AIChatHelpers.quickSuggestions.forEach { suggestion ->
                AssistChip(
                    onClick = { onSelectSuggestion(suggestion) },
                    label = { Text(suggestion) },
                    leadingIcon = {
                        Icon(
                            Icons.Default.AutoAwesome,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                    },
                    modifier = Modifier.fillMaxWidth()
                )
            }
        }
    }
}

@Composable
private fun ChatTurnView(
    turn: AIChatTurn,
    onConfirmAction: (String) -> Unit,
    onCancelAction: (String) -> Unit
) {
    if (turn.role == "user") {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End
        ) {
            Box(
                modifier = Modifier
                    .widthIn(max = 280.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(BluePrimary)
                    .padding(horizontal = 14.dp, vertical = 10.dp)
            ) {
                Text(turn.text, color = Color.White, style = MaterialTheme.typography.bodyMedium)
            }
        }
    } else {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Start
        ) {
            Column(modifier = Modifier.widthIn(max = 320.dp)) {
                if (turn.toolStatuses.isNotEmpty()) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        modifier = Modifier.padding(bottom = 6.dp)
                    ) {
                        turn.toolStatuses.forEach { status ->
                            Surface(
                                shape = RoundedCornerShape(8.dp),
                                color = MaterialTheme.colorScheme.surfaceVariant,
                                modifier = Modifier.padding(bottom = 4.dp)
                            ) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                                ) {
                                    when (status.status) {
                                        "running" -> CircularProgressIndicator(modifier = Modifier.size(12.dp), strokeWidth = 1.5.dp)
                                        "error" -> Icon(Icons.Default.Warning, contentDescription = null, tint = RedLive, modifier = Modifier.size(12.dp))
                                        else -> Icon(Icons.Default.CheckCircle, contentDescription = null, tint = Color(0xFF4CAF50), modifier = Modifier.size(12.dp))
                                    }
                                    Spacer(Modifier.width(4.dp))
                                    Text(status.tool, style = MaterialTheme.typography.labelSmall)
                                }
                            }
                        }
                    }
                }

                if (turn.text.isNotBlank()) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(16.dp))
                            .background(MaterialTheme.colorScheme.surfaceVariant)
                            .padding(horizontal = 14.dp, vertical = 10.dp)
                    ) {
                        Text(turn.text, style = MaterialTheme.typography.bodyMedium)
                    }
                }

                turn.actionPreview?.let { action ->
                    Spacer(Modifier.height(8.dp))
                    ActionCardView(
                        action = action,
                        onConfirm = { onConfirmAction(action.actionId) },
                        onCancel = { onCancelAction(action.actionId) }
                    )
                }
            }
        }
    }
}

@Composable
private fun ActionCardView(
    action: AIActionPreviewEntry,
    onConfirm: () -> Unit,
    onCancel: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.FiberManualRecord, contentDescription = null, tint = RedLive, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text(
                    text = action.tool.replace("_", " ").replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.titleSmall.copy(fontWeight = FontWeight.Bold)
                )
            }

            Spacer(Modifier.height(8.dp))

            action.preview.forEach { (k, v) ->
                val strVal = if (v is JsonPrimitive) v.content else v.toString()
                Row(modifier = Modifier.padding(vertical = 2.dp)) {
                    Text(
                        text = "${k.replace("_", " ").replaceFirstChar { it.uppercase() }}: ",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(text = strVal, style = MaterialTheme.typography.labelSmall)
                }
            }

            Spacer(Modifier.height(10.dp))

            when (action.resolution) {
                AIActionResolution.PENDING, AIActionResolution.CONFIRMING -> {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Button(
                            onClick = onConfirm,
                            enabled = action.resolution != AIActionResolution.CONFIRMING,
                            modifier = Modifier.weight(1f)
                        ) {
                            if (action.resolution == AIActionResolution.CONFIRMING) {
                                CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp, color = Color.White)
                            } else {
                                Text("Confirm")
                            }
                        }
                        OutlinedButton(
                            onClick = onCancel,
                            enabled = action.resolution != AIActionResolution.CONFIRMING,
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("Cancel")
                        }
                    }
                }
                AIActionResolution.CONFIRMED -> {
                    Text("Action confirmed and executed.", color = Color(0xFF4CAF50), style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold))
                }
                AIActionResolution.CANCELLED -> {
                    Text("Action cancelled.", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                }
                AIActionResolution.FAILED -> {
                    Text("Action failed.", color = RedLive, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
