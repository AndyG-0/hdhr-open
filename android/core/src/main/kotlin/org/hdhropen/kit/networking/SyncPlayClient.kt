package org.hdhropen.kit.networking

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.hdhropen.kit.models.*
import org.hdhropen.kit.utilities.Log

class SyncPlayClient(
    private val httpClient: OkHttpClient,
    private val json: Json,
    private val coroutineScope: CoroutineScope
) {
    private var webSocket: WebSocket? = null
    private var pingJob: Job? = null
    private var progressJob: Job? = null

    private val _room = MutableStateFlow<SyncPlayRoom?>(null)
    val room: StateFlow<SyncPlayRoom?> = _room.asStateFlow()

    private val _participants = MutableStateFlow<List<SyncPlayParticipant>>(emptyList())
    val participants: StateFlow<List<SyncPlayParticipant>> = _participants.asStateFlow()

    private val _sessionId = MutableStateFlow<String?>(null)
    val sessionId: StateFlow<String?> = _sessionId.asStateFlow()

    private val _isHost = MutableStateFlow(false)
    val isHost: StateFlow<Boolean> = _isHost.asStateFlow()

    private val _pingMs = MutableStateFlow(0.0)
    val pingMs: StateFlow<Double> = _pingMs.asStateFlow()

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    var onRemotePlay: ((position: Double, rate: Double) -> Unit)? = null
    var onRemotePause: ((position: Double) -> Unit)? = null
    var onRemoteSeek: ((position: Double) -> Unit)? = null
    var onRemoteContentChange: ((content: SyncPlayContent) -> Unit)? = null
    var getCurrentPosition: (() -> Double)? = null
    var isPlayerReady: (() -> Boolean)? = null

    fun connect(wsUrl: String) {
        disconnect()

        val request = Request.Builder()
            .url(wsUrl)
            .build()

        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                _isConnected.value = true
                startPingAndProgressJobs()
                Log.network.info("SyncPlay WebSocket connected")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val msg = json.decodeFromString<SyncPlayMessage>(text)
                    handleMessage(msg)
                } catch (e: Exception) {
                    Log.network.error("SyncPlay JSON decode error: ${e.localizedMessage}")
                }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
                handleDisconnected()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.network.error("SyncPlay WebSocket failure: ${t.localizedMessage}")
                handleDisconnected()
            }
        })
    }

    private fun handleMessage(msg: SyncPlayMessage) {
        when (msg.type) {
            "room_state" -> {
                msg.room?.let { r ->
                    _room.value = r
                    _participants.value = r.participants
                    msg.yourSessionId?.let { sid ->
                        _sessionId.value = sid
                        _isHost.value = (r.hostSessionId == sid)
                    }
                }
            }
            "participant_joined" -> {
                msg.participant?.let { p ->
                    val current = _participants.value.toMutableList()
                    if (current.none { it.sessionId == p.sessionId }) {
                        current.add(p)
                        _participants.value = current
                    }
                }
            }
            "participant_left" -> {
                val leftId = msg.sessionId
                if (leftId != null) {
                    val current = _participants.value.filter { it.sessionId != leftId }
                    _participants.value = current
                    msg.newHostSessionId?.let { newHostId ->
                        _isHost.value = (_sessionId.value == newHostId)
                        _participants.value = current.map {
                            if (it.sessionId == newHostId) it.copy(isHost = true) else it
                        }
                    }
                }
            }
            "participant_updated" -> {
                msg.participant?.let { updated ->
                    _participants.value = _participants.value.map {
                        if (it.sessionId == updated.sessionId) updated else it
                    }
                }
            }
            "playback_update" -> {
                val action = msg.action
                val pos = msg.position ?: 0.0
                val rate = msg.playbackRate ?: 1.0
                val isPlaying = msg.isPlaying ?: false
                val serverTime = msg.serverTime ?: 0.0

                _room.value?.let { currentRoom ->
                    _room.value = currentRoom.copy(
                        playbackState = SyncPlayPlaybackState(
                            isPlaying = isPlaying,
                            position = pos,
                            playbackRate = rate,
                            updatedAt = serverTime
                        )
                    )
                }

                // If triggered by a remote peer, apply to local player
                if (msg.triggeredBy != _sessionId.value) {
                    when (action) {
                        "play" -> onRemotePlay?.invoke(pos, rate)
                        "pause" -> onRemotePause?.invoke(pos)
                        "seek" -> onRemoteSeek?.invoke(pos)
                    }
                }
            }
            "content_changed" -> {
                msg.content?.let { c ->
                    onRemoteContentChange?.invoke(c)
                }
                msg.room?.let { r ->
                    _room.value = r
                    _participants.value = r.participants
                }
            }
            "host_changed" -> {
                msg.newHostSessionId?.let { newHostId ->
                    _isHost.value = (_sessionId.value == newHostId)
                    _participants.value = _participants.value.map {
                        it.copy(isHost = it.sessionId == newHostId)
                    }
                }
            }
            "pong" -> {
                val clientTime = msg.clientTime ?: 0.0
                val now = System.currentTimeMillis().toDouble()
                val rtt = now - clientTime
                _pingMs.value = maxOf(1.0, rtt)
            }
        }
    }

    private fun startPingAndProgressJobs() {
        pingJob?.cancel()
        pingJob = coroutineScope.launch(Dispatchers.IO) {
            while (isActive && _isConnected.value) {
                delay(4000)
                val pingObj = mapOf(
                    "type" to "ping",
                    "client_time" to System.currentTimeMillis().toDouble()
                )
                sendMessage(pingObj)
            }
        }

        progressJob?.cancel()
        progressJob = coroutineScope.launch(Dispatchers.IO) {
            while (isActive && _isConnected.value) {
                delay(2000)
                val pos = getCurrentPosition?.invoke() ?: 0.0
                val ready = isPlayerReady?.invoke() ?: true
                val progressObj = mapOf(
                    "type" to "progress",
                    "position" to pos,
                    "is_ready" to ready,
                    "ping_ms" to _pingMs.value
                )
                sendMessage(progressObj)
            }
        }
    }

    fun sendPlay(position: Double, playbackRate: Double = 1.0) {
        sendMessage(mapOf(
            "type" to "play",
            "position" to position,
            "playback_rate" to playbackRate
        ))
    }

    fun sendPause(position: Double) {
        sendMessage(mapOf(
            "type" to "pause",
            "position" to position
        ))
    }

    fun sendSeek(position: Double) {
        sendMessage(mapOf(
            "type" to "seek",
            "position" to position
        ))
    }

    fun changeContent(content: SyncPlayContent) {
        val jsonContent = json.encodeToString(SyncPlayContent.serializer(), content)
        sendMessage(mapOf(
            "type" to "change_content",
            "content" to jsonContent
        ))
    }

    fun transferHost(targetSessionId: String) {
        sendMessage(mapOf(
            "type" to "transfer_host",
            "target_session_id" to targetSessionId
        ))
    }

    private fun sendMessage(map: Map<String, Any>) {
        try {
            val str = map.entries.joinToString(prefix = "{", postfix = "}") { (k, v) ->
                val vStr = when (v) {
                    is Number, is Boolean -> v.toString()
                    is String -> if (v.startsWith("{")) v else "\"$v\""
                    else -> "\"$v\""
                }
                "\"$k\":$vStr"
            }
            webSocket?.send(str)
        } catch (e: Exception) {
            Log.network.error("Error sending SyncPlay message: ${e.localizedMessage}")
        }
    }

    private fun handleDisconnected() {
        _isConnected.value = false
        _room.value = null
        _participants.value = emptyList()
        _sessionId.value = null
        _isHost.value = false
        pingJob?.cancel()
        progressJob?.cancel()
    }

    fun disconnect() {
        try {
            webSocket?.send("""{"type":"leave"}""")
            webSocket?.close(1000, "User left")
        } catch (_: Exception) {}
        webSocket = null
        handleDisconnected()
    }
}
