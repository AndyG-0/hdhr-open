package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.cancelAIAction
import org.hdhropen.kit.networking.confirmAIAction
import org.hdhropen.kit.networking.sendAIChat

class AIAssistantViewModel(
    val apiClient: APIClient,
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO
) : ViewModel() {

    private val _turns = MutableStateFlow<List<AIChatTurn>>(emptyList())
    val turns: StateFlow<List<AIChatTurn>> = _turns.asStateFlow()

    private val _isSending = MutableStateFlow(false)
    val isSending: StateFlow<Boolean> = _isSending.asStateFlow()

    private val _errorText = MutableStateFlow<String?>(null)
    val errorText: StateFlow<String?> = _errorText.asStateFlow()

    private var chatJob: Job? = null

    fun sendPrompt(prompt: String) {
        val trimmed = prompt.trim()
        if (trimmed.isBlank() || _isSending.value) return

        _errorText.value = null

        val currentTurns = _turns.value.toMutableList()
        val priorWire = AIChatHelpers.toWireMessages(currentTurns)
        val wire = priorWire.toMutableList().apply {
            add(AIChatWireMessage(role = "user", content = JsonPrimitive(trimmed)))
        }

        val userTurn = AIChatTurn(role = "user", text = trimmed)
        val assistantTurn = AIChatTurn(role = "assistant", text = "")
        currentTurns.add(userTurn)
        currentTurns.add(assistantTurn)
        _turns.value = currentTurns.toList()

        val assistantIndex = currentTurns.size - 1
        _isSending.value = true

        chatJob?.cancel()
        chatJob = viewModelScope.launch {
            try {
                apiClient.sendAIChat(AIChatRequest(messages = wire), ioDispatcher = ioDispatcher) { event ->
                    val turnsList = _turns.value.toMutableList()
                    if (assistantIndex >= turnsList.size) return@sendAIChat
                    val turn = turnsList[assistantIndex]

                    when (event.type) {
                        "token" -> {
                            event.text?.let { t ->
                                turnsList[assistantIndex] = turn.copy(text = turn.text + t)
                                _turns.value = turnsList
                            }
                        }
                        "tool_call" -> {
                            val callId = event.id
                            val tool = event.tool
                            if (callId != null && tool != null) {
                                val updatedCalls = turn.toolCalls.toMutableList().apply {
                                    add(AIToolCallRecord(id = callId, name = tool, arguments = event.arguments ?: emptyMap()))
                                }
                                turnsList[assistantIndex] = turn.copy(toolCalls = updatedCalls)
                                _turns.value = turnsList
                            }
                        }
                        "tool_status" -> {
                            val tool = event.tool
                            val status = event.status
                            if (tool != null && status != null) {
                                val updatedStatuses = turn.toolStatuses.toMutableList()
                                val existing = updatedStatuses.indexOfFirst { it.tool == tool }
                                if (existing != -1) {
                                    updatedStatuses[existing].status = status
                                    updatedStatuses[existing].message = event.message
                                } else {
                                    updatedStatuses.add(AIToolStatusEntry(tool = tool, status = status, message = event.message))
                                }
                                turnsList[assistantIndex] = turn.copy(toolStatuses = updatedStatuses)
                                _turns.value = turnsList
                            }
                        }
                        "tool_result" -> {
                            val callId = event.id
                            val content = event.content
                            if (callId != null && content != null) {
                                val updatedCalls = turn.toolCalls.toMutableList()
                                val rec = updatedCalls.indexOfFirst { it.id == callId }
                                if (rec != -1) {
                                    updatedCalls[rec].result = content
                                    turnsList[assistantIndex] = turn.copy(toolCalls = updatedCalls)
                                    _turns.value = turnsList
                                }
                            }
                        }
                        "action_preview" -> {
                            val actId = event.actionId
                            val tool = event.tool
                            val prev = event.preview
                            if (actId != null && tool != null && prev != null) {
                                turnsList[assistantIndex] = turn.copy(
                                    actionPreview = AIActionPreviewEntry(
                                        actionId = actId,
                                        tool = tool,
                                        preview = prev,
                                        resolution = AIActionResolution.PENDING
                                    )
                                )
                                _turns.value = turnsList
                            }
                        }
                        "error" -> {
                            event.message?.let { _errorText.value = it }
                        }
                        "done" -> {
                            _isSending.value = false
                        }
                    }
                }
            } catch (e: Exception) {
                _errorText.value = e.localizedMessage ?: "Failed to get AI response"
            } finally {
                _isSending.value = false
            }
        }
    }

    fun confirmAction(actionId: String) {
        val turnsList = _turns.value.toMutableList()
        val turnIdx = turnsList.indexOfFirst { it.actionPreview?.actionId == actionId }
        if (turnIdx != -1) {
            val t = turnsList[turnIdx]
            turnsList[turnIdx] = t.copy(actionPreview = t.actionPreview?.copy(resolution = AIActionResolution.CONFIRMING))
            _turns.value = turnsList

            viewModelScope.launch {
                try {
                    apiClient.confirmAIAction(actionId)
                    val updated = _turns.value.toMutableList()
                    if (turnIdx < updated.size) {
                        updated[turnIdx] = updated[turnIdx].copy(
                            actionPreview = updated[turnIdx].actionPreview?.copy(resolution = AIActionResolution.CONFIRMED)
                        )
                        _turns.value = updated
                    }
                } catch (e: Exception) {
                    val updated = _turns.value.toMutableList()
                    if (turnIdx < updated.size) {
                        updated[turnIdx] = updated[turnIdx].copy(
                            actionPreview = updated[turnIdx].actionPreview?.copy(resolution = AIActionResolution.FAILED)
                        )
                        _turns.value = updated
                    }
                }
            }
        }
    }

    fun cancelAction(actionId: String) {
        val turnsList = _turns.value.toMutableList()
        val turnIdx = turnsList.indexOfFirst { it.actionPreview?.actionId == actionId }
        if (turnIdx != -1) {
            val t = turnsList[turnIdx]
            turnsList[turnIdx] = t.copy(actionPreview = t.actionPreview?.copy(resolution = AIActionResolution.CANCELLED))
            _turns.value = turnsList

            viewModelScope.launch {
                try {
                    apiClient.cancelAIAction(actionId)
                } catch (e: Exception) {
                    // Ignore
                }
            }
        }
    }

    fun newChat() {
        chatJob?.cancel()
        chatJob = null
        _turns.value = emptyList()
        _errorText.value = null
        _isSending.value = false
    }
}
