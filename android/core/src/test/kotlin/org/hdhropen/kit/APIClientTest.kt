package org.hdhropen.kit

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.Cookie
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

class APIClientTest {

    private lateinit var server: MockWebServer
    private lateinit var client: APIClient
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val url = server.url("/").toString().removeSuffix("/")
        client = APIClient(baseURL = url)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    // MARK: - InMemoryCookieJar Tests

    @Test
    fun testInMemoryCookieJar_saveAndLoadCookies() {
        val jar = InMemoryCookieJar()
        val url = "http://example.com/api".toHttpUrl()

        val cookie1 = Cookie.Builder()
            .domain("example.com")
            .name("session")
            .value("12345")
            .expiresAt(System.currentTimeMillis() + 100000)
            .build()

        jar.saveFromResponse(url, listOf(cookie1))
        val loaded = jar.loadForRequest(url)
        assertEquals(1, loaded.size)
        assertEquals("session", loaded[0].name)
        assertEquals("12345", loaded[0].value)

        // Replace cookie with same name
        val cookie2 = Cookie.Builder()
            .domain("example.com")
            .name("session")
            .value("67890")
            .expiresAt(System.currentTimeMillis() + 100000)
            .build()
        jar.saveFromResponse(url, listOf(cookie2))
        val loaded2 = jar.loadForRequest(url)
        assertEquals(1, loaded2.size)
        assertEquals("67890", loaded2[0].value)

        // Expired cookie
        val expiredCookie = Cookie.Builder()
            .domain("example.com")
            .name("expired")
            .value("dead")
            .expiresAt(System.currentTimeMillis() - 1000)
            .build()
        jar.saveFromResponse(url, listOf(expiredCookie))
        val loaded3 = jar.loadForRequest(url)
        assertFalse(loaded3.any { it.name == "expired" })

        // Clear
        jar.clear()
        assertTrue(jar.loadForRequest(url).isEmpty())
    }

    // MARK: - Request Engine & Header Tests

    @Test
    fun testRequestHeaders_bearerTokenAndDeviceId() = runBlocking {
        client.bearerToken = "secret-token"
        client.deviceId = "device-xyz"

        server.enqueue(MockResponse().setResponseCode(200).setBody("[]"))
        client.listRecordings()

        val recorded = server.takeRequest(5, TimeUnit.SECONDS)
        assertNotNull(recorded)
        assertEquals("Bearer secret-token", recorded?.getHeader("Authorization"))
        assertEquals("device-xyz", recorded?.getHeader("X-Device-Id"))
    }

    @Test
    fun testRequestRaw_customHeadersAndMethods() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody("OK"))
        val response = client.requestRaw(
            path = "/test",
            method = "POST",
            jsonBody = "{\"key\":\"val\"}",
            headers = mapOf("Custom-Header" to "CustomVal")
        )
        assertEquals("OK", String(response))

        val recorded = server.takeRequest(5, TimeUnit.SECONDS)
        assertEquals("POST", recorded?.method)
        assertEquals("CustomVal", recorded?.getHeader("Custom-Header"))
    }

    @Test
    fun testRequestRaw_errorStatusMappings() = runBlocking {
        // 401
        server.enqueue(MockResponse().setResponseCode(401).setBody("{\"detail\":\"Session expired\"}"))
        try {
            client.requestRaw("/unauth")
            fail("Expected APIError.Unauthorized")
        } catch (e: APIError.Unauthorized) {
            assertEquals("Session expired", e.message)
        }

        // 403
        server.enqueue(MockResponse().setResponseCode(403).setBody("Forbidden"))
        try {
            client.requestRaw("/forbidden")
            fail("Expected APIError.Forbidden")
        } catch (e: APIError.Forbidden) {
            // Success
        }

        // 404
        server.enqueue(MockResponse().setResponseCode(404).setBody("{\"detail\":\"Not here\"}"))
        try {
            client.requestRaw("/missing")
            fail("Expected APIError.NotFound")
        } catch (e: APIError.NotFound) {
            assertEquals("Not here", e.message)
        }

        // 429
        server.enqueue(MockResponse().setResponseCode(429).setBody("{\"detail\":\"Rate limit\"}"))
        try {
            client.requestRaw("/ratelimit")
            fail("Expected APIError.LockedOut")
        } catch (e: APIError.LockedOut) {
            assertEquals("Rate limit", e.message)
        }

        // 500
        server.enqueue(MockResponse().setResponseCode(500).setBody("Internal Server Error"))
        try {
            client.requestRaw("/server-err")
            fail("Expected APIError.ServerError")
        } catch (e: APIError.ServerError) {
            assertEquals(500, e.statusCode)
        }
    }

    @Test
    fun testRequest_decodingError() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody("invalid-json"))
        try {
            client.request<HDHomeRunChannelsResponse>("/channels")
            fail("Expected DecodingError")
        } catch (e: APIError.DecodingError) {
            // Expected
        }
    }

    @Test
    fun testFetchRawString() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody("Raw text data"))
        val result = client.fetchRawString("/raw")
        assertEquals("Raw text data", result)
    }

    // MARK: - Guide APIs

    @Test
    fun testGuideAPIs() = runBlocking {
        val channels = listOf(
            HDHomeRunChannel(channelNumber = "2.1", name = "CBS")
        )
        val response = HDHomeRunChannelsResponse(channels = channels)
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(response)))

        val result = client.getChannels()
        assertEquals(1, result.channels.size)
        assertEquals("2.1", result.channels[0].channelNumber)
        server.takeRequest()

        // getGuide
        val guideChannels = listOf(
            HDHomeRunFullGuideChannel(channelNumber = "2.1", channelName = "CBS", airings = emptyList())
        )
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(guideChannels)))
        val guideResult = client.getGuide()
        assertEquals(1, guideResult.size)
        server.takeRequest()

        // refreshGuide
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))
        client.refreshGuide()
        val refreshReq = server.takeRequest(5, TimeUnit.SECONDS)
        assertEquals("POST", refreshReq?.method)
    }

    // MARK: - DVR APIs

    @Test
    fun testDvrAPIs() = runBlocking {
        val dvrInfo = HDHomeRunDvrInfo(
            freeSpaceBytes = 500000000000L
        )
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(dvrInfo)))
        val dvr = client.getDvrInfo()
        assertEquals(500000000000L, dvr.freeSpaceBytes)
        server.takeRequest()

        // listRecordings
        val recording = HDHomeRunRecording(
            title = "Test Show",
            recordingId = "rec-1",
            channelNumber = "4.1"
        )
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(recording))))
        val recs = client.listRecordings()
        assertEquals(1, recs.size)
        assertEquals("rec-1", recs[0].recordingId)
        server.takeRequest()

        // deleteRecording
        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.deleteRecording("rec-1")
        val delReq = server.takeRequest(5, TimeUnit.SECONDS)
        assertEquals("DELETE", delReq?.method)

        // listRecordingRules
        val rule = HDHomeRunRecordingRule(recordingRuleId = "rule-1", seriesId = "series-1", title = "Show Rule")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(rule))))
        val rules = client.listRecordingRules()
        assertEquals(1, rules.size)

        // addRecordingRule
        val payload = AddRecordingRulePayload(seriesId = "series-1")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(rule))))
        val addedRules = client.addRecordingRule(payload)
        assertEquals(1, addedRules.size)

        // updateRecordingRule
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(rule))))
        val updatedRules = client.updateRecordingRule("rule-1", payload)
        assertEquals(1, updatedRules.size)

        // deleteRecordingRule
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(emptyList<HDHomeRunRecordingRule>())))
        val emptyRules = client.deleteRecordingRule("rule-1")
        assertTrue(emptyRules.isEmpty())
    }

    // MARK: - Live Watch APIs

    @Test
    fun testLiveWatchAPIs() = runBlocking {
        val watchRec = HDHomeRunRecording(
            recordingId = "watch-1",
            sessionId = "sess-123",
            title = "Live TV"
        )
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(watchRec)))
        val started = client.startWatch("5.1")
        assertNotNull(started)
        assertEquals("sess-123", started?.sessionId)

        // startWatch failure returns null
        server.enqueue(MockResponse().setResponseCode(500).setBody("Server Error"))
        val failed = client.startWatch("5.1")
        assertNull(failed)

        // heartbeatWatch
        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.heartbeatWatch("sess-123")
        val hbReq = server.takeRequest(5, TimeUnit.SECONDS)
        assertEquals("POST", hbReq?.method)

        // stopWatch
        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.stopWatch("sess-123")
        val stopReq = server.takeRequest(5, TimeUnit.SECONDS)
        assertEquals("POST", stopReq?.method)

        // promoteWatch
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(watchRec)))
        val promoted = client.promoteWatch("sess-123", mapOf("padding" to buildJsonObject { put("val", 5) }))
        assertEquals("watch-1", promoted.recordingId)
    }

    // MARK: - HLS & Tuner APIs

    @Test
    fun testHLSAndTunerAPIs() = runBlocking {
        val hlsResp = HLSSessionResponse(sessionId = "hls-1", playlistUrl = "http://example.com/playlist.m3u8")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(hlsResp)))
        val hls = client.createRecordingHLSSession(url = "http://example.com/stream.ts", recordingId = "rec-1")
        assertEquals("hls-1", hls.sessionId)

        server.enqueue(MockResponse().setResponseCode(204).setBody(""))
        client.heartbeatHLSSession("hls-1")

        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.stopHLSSession("hls-1")

        // Tuner Status
        val tuner = HDHomeRunTuner(index = 0, resource = "tuner0", signalQualityPercent = 95)
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(tuner))))
        val tuners = client.getTunerStatus()
        assertEquals(1, tuners.size)
        assertEquals(95, tuners[0].signalQualityPercent)
    }

    // MARK: - Auth & User Profiles

    @Test
    fun testAuthAndUserProfiles() = runBlocking {
        val profile = UserProfile(id = "user-1", name = "Alice", hasPin = false)
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(profile))))
        val profiles = client.listProfiles()
        assertEquals(1, profiles.size)
        assertEquals("Alice", profiles[0].name)

        // Login
        val user = CurrentUser(id = "user-1", name = "Alice", token = "alice-token")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(user)))
        val loggedIn = client.login("user-1", pin = null, tokenName = "AndroidPhone")
        assertEquals("Alice", loggedIn.name)
        assertEquals("alice-token", loggedIn.token)

        // Logout
        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.logout()

        // Current User
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(user)))
        val current = client.getCurrentUser()
        assertEquals("user-1", current.id)

        // User Preferences
        val prefs = UserPreferences(theme = "dark", locale = "en")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(prefs)))
        val loadedPrefs = client.getUserPreferences()
        assertEquals("dark", loadedPrefs.theme)

        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(prefs)))
        val updatedPrefs = client.updateUserPreferences(prefs)
        assertEquals("dark", updatedPrefs.theme)
    }

    // MARK: - Device & Settings APIs

    @Test
    fun testDeviceAndSettingsAPIs() = runBlocking {
        val regResult = DeviceRegisterResult(id = "dev-100", name = "Pixel")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(regResult)))
        val reg = client.registerDevice()
        assertEquals("dev-100", reg.id)
        assertEquals("dev-100", client.deviceId)

        val devInfo = DeviceInfo(id = "dev-100", name = "Pixel")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(devInfo)))
        val currentDev = client.getCurrentDevice()
        assertEquals("dev-100", currentDev.id)

        server.enqueue(MockResponse().setResponseCode(200).setBody("[]"))
        val devList = client.listDevices()
        assertTrue(devList.isEmpty())

        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.deleteDevice("dev-100")

        // Settings
        val settings = AppSettings(timezone = "UTC", guideProviderPriority = "hdhr")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(settings)))
        val loadedSettings = client.getSettings()
        assertEquals("UTC", loadedSettings.timezone)

        // Transcode Presets
        val preset = HDHomeRunTranscodePreset(id = "1080p", label = "1080p HD", description = "1080p transcode")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(preset))))
        val presets = client.getTranscodePresets()
        assertEquals(1, presets.size)

        // SyncPlay WebSocket URL
        val wsUrl = client.syncPlayWsUrl("room-abc", "User1")
        assertTrue(wsUrl.contains("room-abc"))
        assertTrue(wsUrl.startsWith("ws://") || wsUrl.startsWith("wss://"))
    }

    // MARK: - AI APIs & SSE Streaming

    @Test
    fun testAIStreamingAndActions() = runBlocking {
        val sseResponse = buildString {
            append("data: {\"type\":\"delta\",\"text\":\"Hello \"}\n\n")
            append("data: {\"type\":\"delta\",\"text\":\"World!\"}\n\n")
            append("data: {\"type\":\"done\"}\n\n")
        }
        server.enqueue(MockResponse().setResponseCode(200).setBody(sseResponse))

        val events = mutableListOf<AIStreamEvent>()
        client.sendAIChat(AIChatRequest(messages = listOf(AIChatWireMessage(role = "user", content = kotlinx.serialization.json.JsonPrimitive("Hi"))))) { event ->
            events.add(event)
        }

        assertEquals(3, events.size)
        assertEquals("Hello ", events[0].text)
        assertEquals("World!", events[1].text)
        assertEquals("done", events[2].type)

        // Confirm AI Action
        val confirmResp = AIConfirmActionResponse(result = kotlinx.serialization.json.JsonPrimitive("ok"))
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(confirmResp)))
        val confirmed = client.confirmAIAction("action-1")
        assertNotNull(confirmed.result)

        // Cancel AI Action
        val cancelResp = AICancelActionResponse(ok = true)
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(cancelResp)))
        val cancelled = client.cancelAIAction("action-1")
        assertTrue(cancelled.ok)
    }

    @Test
    fun testRemainingAPIsAndHttpMethods() = runBlocking {
        // Absolute URL fetchRawString
        val absUrl = server.url("/static/caption.vtt").toString()
        server.enqueue(MockResponse().setResponseCode(200).setBody("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello"))
        val vtt = client.fetchRawString(absUrl)
        assertTrue(vtt.startsWith("WEBVTT"))

        // refreshGuide (POST)
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))
        client.refreshGuide()

        // heartbeatWatch, stopWatch, promoteWatch
        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.heartbeatWatch("sess_hb")

        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.stopWatch("sess_stop")

        val promRec = HDHomeRunRecording(recordingId = "prom_1", title = "Promoted")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(promRec)))
        val promoted = client.promoteWatch("sess_prom", mapOf("opt" to kotlinx.serialization.json.JsonPrimitive("val")))
        assertEquals("prom_1", promoted.recordingId)

        // stopHLSSession
        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.stopHLSSession("hls_sess")

        // updateRecordingRule (PUT)
        val rule = HDHomeRunRecordingRule(recordingRuleId = "r1", seriesId = "s1", title = "Show")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(rule))))
        val updatedRules = client.updateRecordingRule("r1", AddRecordingRulePayload(seriesId = "s1"))
        assertEquals(1, updatedRules.size)

        // listProfiles, getCurrentUser, logout
        val prof = UserProfile(id = "p1", name = "Test")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(prof))))
        val profiles = client.listProfiles()
        assertEquals(1, profiles.size)

        val curr = CurrentUser(id = "p1", name = "Test")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(curr)))
        val current = client.getCurrentUser()
        assertEquals("p1", current.id)

        server.enqueue(MockResponse().setResponseCode(200).setBody(""))
        client.logout()

        // updateUserPreferences (PATCH)
        val newPrefs = UserPreferences(theme = "dark")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(newPrefs)))
        val updatedPrefs = client.updateUserPreferences(newPrefs)
        assertEquals("dark", updatedPrefs.theme)

        // HWAccelDiagnostics
        val diag = HWAccelDiagnostics(device = "vaapi", summary = listOf("ok"))
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(diag)))
        val loadedDiag = client.getHWAccelDiagnostics()
        assertEquals("vaapi", loadedDiag.device)

        // Network integrations
        val netInt = NetworkIntegration(id = "net1", type = "hdhr", name = "Tuner")
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(listOf(netInt))))
        val listInts = client.listNetworkIntegrations()
        assertEquals(1, listInts.size)

        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(netInt)))
        val singleInt = client.getNetworkIntegration("hdhr")
        assertEquals("net1", singleInt.id)

        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(netInt)))
        val patchedInt = client.updateNetworkIntegration("hdhr", emptyMap())
        assertEquals("net1", patchedInt.id)

        // SyncPlay Room APIs
        val room = SyncPlayRoom(
            roomCode = "ROOMX",
            hostSessionId = "s1",
            playbackState = SyncPlayPlaybackState(isPlaying = true, position = 10.0),
            participants = emptyList()
        )
        val createResp = CreateSyncPlayRoomResponse(roomCode = "ROOMX", room = room)
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(createResp)))
        val createdRoom = client.createSyncPlayRoom(SyncPlayContent(type = "channel", id = "4.1"), "Alice")
        assertEquals("ROOMX", createdRoom.room.roomCode)

        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(room)))
        val fetchedRoom = client.getSyncPlayRoom("ROOMX")
        assertEquals("ROOMX", fetchedRoom.roomCode)
    }
}
