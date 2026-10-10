package org.hdhropen.kit.networking

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.JsonElement
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.utilities.Log

class WatchSessionManager(
    private val apiClient: APIClient,
    coroutineScope: CoroutineScope? = null,
    private val ioDispatcher: CoroutineDispatcher = Dispatchers.IO
) {
    // Only a scope WE created (the no-arg-default case, used by
    // AppEnvironment's app-lifetime instance) is ours to cancel - a scope a
    // caller passed in explicitly (e.g. a ViewModel's `viewModelScope`, or a
    // test's `TestScope`) is owned by that caller and must outlive calls to
    // cancel() here.
    private val ownsCoroutineScope = coroutineScope == null
    private val coroutineScope: CoroutineScope = coroutineScope ?: CoroutineScope(Dispatchers.Main + SupervisorJob())
    private val _activeSessionId = MutableStateFlow<String?>(null)
    val activeSessionId: StateFlow<String?> = _activeSessionId.asStateFlow()

    private val _activeRecordingId = MutableStateFlow<String?>(null)
    val activeRecordingId: StateFlow<String?> = _activeRecordingId.asStateFlow()

    private val _isPromoted = MutableStateFlow(false)
    val isPromoted: StateFlow<Boolean> = _isPromoted.asStateFlow()

    private var heartbeatJob: Job? = null

    suspend fun startWatch(channelNumber: String): HDHomeRunRecording? {
        stopWatch()
        _isPromoted.value = false

        val recording = apiClient.startWatch(channelNumber)
        val sessionId = recording?.sessionId
        val recId = recording?.recordingId

        if (sessionId != null && recId != null) {
            _activeSessionId.value = sessionId
            _activeRecordingId.value = recId
            startHeartbeat(sessionId)
            Log.player.info("Started watch session $sessionId for channel $channelNumber")
        }
        return recording
    }

    private fun startHeartbeat(sessionId: String) {
        heartbeatJob?.cancel()
        heartbeatJob = coroutineScope.launch(ioDispatcher) {
            while (isActive && !_isPromoted.value) {
                delay(20_000) // 20s
                if (!isActive || _isPromoted.value) break
                try {
                    apiClient.heartbeatWatch(sessionId)
                    Log.player.debug("Heartbeat sent for watch session $sessionId")
                } catch (e: Exception) {
                    Log.player.warning("Heartbeat failed for $sessionId: ${e.localizedMessage}")
                }
            }
        }
    }

    suspend fun promoteWatch(options: Map<String, JsonElement>? = null): HDHomeRunRecording {
        val sessionId = _activeSessionId.value ?: throw APIError.NoActiveWatchSession

        val recording = apiClient.promoteWatch(sessionId, options)
        _isPromoted.value = true
        heartbeatJob?.cancel()
        heartbeatJob = null
        Log.player.info("Watch session $sessionId promoted to permanent DVR recording!")
        return recording
    }

    fun stopWatch() {
        heartbeatJob?.cancel()
        heartbeatJob = null

        val sessionId = _activeSessionId.value
        val wasPromoted = _isPromoted.value

        if (sessionId != null && !wasPromoted) {
            coroutineScope.launch(ioDispatcher) {
                try {
                    apiClient.stopWatch(sessionId)
                    Log.player.info("Stopped watch session $sessionId")
                } catch (e: Exception) {
                    Log.player.debug("Failed to stop watch session $sessionId: ${e.localizedMessage}")
                }
            }
        }

        _activeSessionId.value = null
        _activeRecordingId.value = null
        _isPromoted.value = false
    }

    /**
     * Cancels this manager's owned [coroutineScope] (heartbeat/stop-watch
     * jobs included). Only cancels the scope if this instance created the
     * default one itself - a scope passed in by the caller (e.g. a
     * ViewModel's `viewModelScope`) is owned by that caller and must not be
     * cancelled here.
     */
    fun cancel() {
        if (ownsCoroutineScope) {
            coroutineScope.cancel()
        }
    }
}
