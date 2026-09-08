package org.hdhropen.kit

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.SyncPlayClient
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.CaptionController
import org.hdhropen.kit.playback.PlayerEngine
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class SyncPlayTest {

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = true
        coerceInputValues = true
    }

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `test SyncPlay models serialization and deserialization`() {
        val room = SyncPlayRoom(
            roomCode = "ABCDEF",
            hostSessionId = "sess-1",
            createdAt = 1000.0,
            playbackState = SyncPlayPlaybackState(
                isPlaying = true,
                position = 42.5,
                playbackRate = 1.0,
                updatedAt = 1005.0
            ),
            content = SyncPlayContent(
                type = "recording",
                id = "rec-123",
                title = "Live Show",
                channelNumber = "5.1"
            ),
            participants = listOf(
                SyncPlayParticipant(
                    sessionId = "sess-1",
                    userName = "Alice",
                    isHost = true,
                    isReady = true,
                    position = 42.5,
                    pingMs = 15.0
                )
            )
        )

        val encoded = json.encodeToString(room)
        val decoded = json.decodeFromString<SyncPlayRoom>(encoded)

        assertEquals("ABCDEF", decoded.roomCode)
        assertEquals("sess-1", decoded.hostSessionId)
        assertTrue(decoded.playbackState.isPlaying)
        assertEquals(42.5, decoded.playbackState.position, 0.001)
        assertEquals("rec-123", decoded.content?.recordingId ?: decoded.content?.id)
        assertEquals(1, decoded.participants.size)
        assertEquals("Alice", decoded.participants[0].userName)
        assertTrue(decoded.participants[0].isHost)
    }

    @Test
    fun `test SyncPlay message decoding for room_state and playback_update`() {
        val jsonStr = """
            {
                "type": "room_state",
                "your_session_id": "sess-2",
                "room": {
                    "room_code": "XYZ789",
                    "host_session_id": "sess-1",
                    "created_at": 100.0,
                    "content": {
                        "type": "channel",
                        "id": "5.1",
                        "title": "News"
                    },
                    "playback_state": {
                        "is_playing": false,
                        "position": 10.0,
                        "playback_rate": 1.0,
                        "updated_at": 105.0
                    },
                    "participants": [
                        {"session_id": "sess-1", "user_name": "HostUser", "is_host": true},
                        {"session_id": "sess-2", "user_name": "Joiner", "is_host": false}
                    ]
                }
            }
        """.trimIndent()

        val msg = json.decodeFromString<SyncPlayMessage>(jsonStr)
        assertEquals("room_state", msg.type)
        assertEquals("sess-2", msg.yourSessionId)
        assertNotNull(msg.room)
        assertEquals("XYZ789", msg.room?.roomCode)
        assertEquals(2, msg.room?.participants?.size)
    }

    @Test
    fun `test SyncPlayClient message handling`() {
        val client = SyncPlayClient(
            httpClient = OkHttpClient(),
            json = json,
            coroutineScope = kotlinx.coroutines.CoroutineScope(Dispatchers.Unconfined)
        )

        var playReceived = false
        var playPos = 0.0
        client.onRemotePlay = { pos, _ ->
            playReceived = true
            playPos = pos
        }

        // Simulate receiving room_state via private handleMessage
        val handleMessageMethod = SyncPlayClient::class.java.getDeclaredMethod("handleMessage", SyncPlayMessage::class.java)
        handleMessageMethod.isAccessible = true

        val roomMsg = SyncPlayMessage(
            type = "room_state",
            yourSessionId = "my-sess",
            room = SyncPlayRoom(
                roomCode = "TEST01",
                hostSessionId = "other-sess",
                createdAt = 10.0,
                content = SyncPlayContent(type = "channel", id = "4.1"),
                playbackState = SyncPlayPlaybackState(isPlaying = false, position = 0.0),
                participants = listOf(
                    SyncPlayParticipant(sessionId = "other-sess", userName = "Other", isHost = true),
                    SyncPlayParticipant(sessionId = "my-sess", userName = "Me", isHost = false)
                )
            )
        )
        handleMessageMethod.invoke(client, roomMsg)

        assertEquals("TEST01", client.room.value?.roomCode)
        assertEquals(2, client.participants.value.size)
        assertEquals("my-sess", client.sessionId.value)
        assertFalse(client.isHost.value)

        // Simulate receiving remote playback play action
        val playMsg = SyncPlayMessage(
            type = "playback_update",
            action = "play",
            position = 55.0,
            isPlaying = true,
            triggeredBy = "other-sess"
        )
        handleMessageMethod.invoke(client, playMsg)

        assertTrue(playReceived)
        assertEquals(55.0, playPos, 0.001)
        assertTrue(client.room.value?.playbackState?.isPlaying == true)
        assertEquals(55.0, client.room.value?.playbackState?.position ?: 0.0, 0.001)
    }

    @Test
    fun `test PlayerViewModel SyncPlay wiring`() {
        val apiClient = APIClient("http://localhost:8000")
        val watchSessionManager = WatchSessionManager(apiClient)
        val playerEngine = PlayerEngine().apply { setSeekable(true) }
        val captionController = CaptionController()
        val vm = PlayerViewModel(apiClient, watchSessionManager, playerEngine, captionController)
        vm.playerEngine.loadMedia(url = "http://example.com/test.m3u8", isLive = false, isSeekable = true)

        assertNotNull(vm.syncPlayClient)
        assertNull(vm.syncPlayRoom.value)
        assertFalse(vm.syncPlayConnected.value)

        // Test remote callbacks wired to engine
        vm.syncPlayClient.onRemotePlay?.invoke(12.0, 1.0)
        assertEquals(12.0, vm.playerEngine.currentTime.value, 0.001)

        vm.syncPlayClient.onRemotePause?.invoke(15.0)
        assertEquals(15.0, vm.playerEngine.currentTime.value, 0.001)

        vm.syncPlayClient.onRemoteSeek?.invoke(30.0)
        assertEquals(30.0, vm.playerEngine.currentTime.value, 0.001)
    }

    @Test
    fun `test SyncPlayClient handles all message types and transitions`() {
        val client = SyncPlayClient(
            httpClient = OkHttpClient(),
            json = json,
            coroutineScope = kotlinx.coroutines.CoroutineScope(Dispatchers.Unconfined)
        )

        val handleMessageMethod = SyncPlayClient::class.java.getDeclaredMethod("handleMessage", SyncPlayMessage::class.java)
        handleMessageMethod.isAccessible = true

        var pausedPos: Double? = null
        var seekPos: Double? = null
        var changedContent: SyncPlayContent? = null

        client.onRemotePause = { pos -> pausedPos = pos }
        client.onRemoteSeek = { pos -> seekPos = pos }
        client.onRemoteContentChange = { c -> changedContent = c }

        // 1. Initial Room State
        val roomMsg = SyncPlayMessage(
            type = "room_state",
            yourSessionId = "my-sess",
            room = SyncPlayRoom(
                roomCode = "ROOM01",
                hostSessionId = "host-sess",
                createdAt = 10.0,
                content = SyncPlayContent(type = "channel", id = "4.1"),
                playbackState = SyncPlayPlaybackState(isPlaying = false, position = 0.0),
                participants = listOf(
                    SyncPlayParticipant(sessionId = "host-sess", userName = "Host", isHost = true),
                    SyncPlayParticipant(sessionId = "my-sess", userName = "Me", isHost = false)
                )
            )
        )
        handleMessageMethod.invoke(client, roomMsg)
        assertEquals("ROOM01", client.room.value?.roomCode)
        assertFalse(client.isHost.value)

        // 2. Participant Joined
        val joinMsg = SyncPlayMessage(
            type = "participant_joined",
            participant = SyncPlayParticipant(sessionId = "user-3", userName = "Third", isHost = false)
        )
        handleMessageMethod.invoke(client, joinMsg)
        assertEquals(3, client.participants.value.size)

        // Duplicate join is a no-op
        handleMessageMethod.invoke(client, joinMsg)
        assertEquals(3, client.participants.value.size)

        // 3. Participant Updated
        val updateMsg = SyncPlayMessage(
            type = "participant_updated",
            participant = SyncPlayParticipant(sessionId = "user-3", userName = "Third Renamed", isHost = false, pingMs = 45.0)
        )
        handleMessageMethod.invoke(client, updateMsg)
        assertEquals("Third Renamed", client.participants.value.first { it.sessionId == "user-3" }.userName)
        assertEquals(45.0, client.participants.value.first { it.sessionId == "user-3" }.pingMs, 0.001)

        // 4. Remote Pause and Seek
        val pauseMsg = SyncPlayMessage(
            type = "playback_update",
            action = "pause",
            position = 22.5,
            isPlaying = false,
            triggeredBy = "host-sess"
        )
        handleMessageMethod.invoke(client, pauseMsg)
        assertEquals(22.5, pausedPos)
        assertFalse(client.room.value?.playbackState?.isPlaying ?: true)

        val seekMsg = SyncPlayMessage(
            type = "playback_update",
            action = "seek",
            position = 99.0,
            isPlaying = false,
            triggeredBy = "host-sess"
        )
        handleMessageMethod.invoke(client, seekMsg)
        assertEquals(99.0, seekPos)

        // Action triggered by local session does not trigger remote callbacks
        pausedPos = null
        val localMsg = SyncPlayMessage(
            type = "playback_update",
            action = "pause",
            position = 30.0,
            triggeredBy = "my-sess"
        )
        handleMessageMethod.invoke(client, localMsg)
        assertNull(pausedPos)

        // 5. Content Changed
        val newContent = SyncPlayContent(type = "recording", id = "rec-55", title = "Evening News")
        val contentMsg = SyncPlayMessage(
            type = "content_changed",
            content = newContent,
            room = client.room.value?.copy(content = newContent, participants = client.participants.value)
        )
        handleMessageMethod.invoke(client, contentMsg)
        assertEquals("rec-55", changedContent?.id)
        assertEquals("Evening News", client.room.value?.content?.title)

        // 6. Host Changed
        val hostMsg = SyncPlayMessage(
            type = "host_changed",
            newHostSessionId = "my-sess"
        )
        handleMessageMethod.invoke(client, hostMsg)
        assertTrue(client.isHost.value)
        assertTrue(client.participants.value.first { it.sessionId == "my-sess" }.isHost)

        // 7. Participant Left with new host transfer
        val leftMsg = SyncPlayMessage(
            type = "participant_left",
            sessionId = "host-sess",
            newHostSessionId = "my-sess"
        )
        handleMessageMethod.invoke(client, leftMsg)
        assertEquals(2, client.participants.value.size)
        assertTrue(client.isHost.value)

        // 8. Pong message calculates RTT
        val pongMsg = SyncPlayMessage(
            type = "pong",
            clientTime = System.currentTimeMillis() - 50.0
        )
        handleMessageMethod.invoke(client, pongMsg)
        assertTrue(client.pingMs.value >= 1.0)

        // 9. Disconnect clears state
        client.disconnect()
        assertFalse(client.isConnected.value)
        assertNull(client.room.value)
        assertTrue(client.participants.value.isEmpty())
        assertNull(client.sessionId.value)
        assertFalse(client.isHost.value)
    }

    @Test
    fun `test SyncPlayClient outgoing message helpers do not crash when disconnected`() {
        val client = SyncPlayClient(
            httpClient = OkHttpClient(),
            json = json,
            coroutineScope = kotlinx.coroutines.CoroutineScope(Dispatchers.Unconfined)
        )

        // Should be safe no-ops without active websocket
        client.sendPlay(10.0, 1.0)
        client.sendPause(10.0)
        client.sendSeek(20.0)
        client.changeContent(SyncPlayContent(type = "channel", id = "5.1"))
        client.transferHost("target-sess")
        client.disconnect()
    }
}

