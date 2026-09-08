package org.hdhropen.kit

import org.hdhropen.kit.networking.APIEndpoints
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class APIEndpointsTest {

    @Test
    fun testGuideAndDvrEndpoints() {
        assertEquals("/api/guide/channels", APIEndpoints.guideChannels())
        assertEquals("/api/guide", APIEndpoints.guide())
        assertEquals("/api/guide/refresh", APIEndpoints.refreshGuide())
        assertEquals("/api/dvr/info", APIEndpoints.dvrInfo())
        assertEquals("/api/dvr/recordings", APIEndpoints.recordings())
        assertEquals("/api/dvr/recordings/rec_123", APIEndpoints.deleteRecording("rec_123"))
    }

    @Test
    fun testRecordingDetailEndpoints() {
        val minimal = APIEndpoints.recordingDetail("http://example.com/stream 1", "rec_123")
        assertTrue(minimal.startsWith("/api/dvr/recording-detail?"))
        assertTrue(minimal.contains("url=http%3A%2F%2Fexample.com%2Fstream+1"))
        assertTrue(minimal.contains("recording_id=rec_123"))

        val full = APIEndpoints.recordingDetail(
            url = "http://example.com",
            recordingId = "rec_123",
            start = 100.0,
            recordEnd = 200.0,
            provider = "xmltv"
        )
        assertTrue(full.contains("start=100.0"))
        assertTrue(full.contains("record_end=200.0"))
        assertTrue(full.contains("provider=xmltv"))
    }

    @Test
    fun testRecordingCaptionsAndThumbnailsEndpoints() {
        val captionsMin = APIEndpoints.recordingCaptions("http://example.com", "rec_123")
        assertTrue(captionsMin.startsWith("/api/dvr/recording-captions.vtt?"))

        val captionsFull = APIEndpoints.recordingCaptions("http://example.com", "rec_123", 500.0, "provider_a")
        assertTrue(captionsFull.contains("record_end=500.0"))
        assertTrue(captionsFull.contains("provider=provider_a"))

        val vttMin = APIEndpoints.recordingThumbnailsVtt("http://example.com", "rec_123")
        assertEquals("/api/dvr/recording-thumbnails/rec_123.vtt?url=http%3A%2F%2Fexample.com", vttMin)

        val vttFull = APIEndpoints.recordingThumbnailsVtt("http://example.com", "rec_123", 50.0)
        assertTrue(vttFull.contains("record_end=50.0"))

        val jpgMin = APIEndpoints.recordingThumbnailsJpg("http://example.com", "rec_123")
        assertEquals("/api/dvr/recording-thumbnails/rec_123.jpg?url=http%3A%2F%2Fexample.com", jpgMin)

        val jpgFull = APIEndpoints.recordingThumbnailsJpg("http://example.com", "rec_123", 50.0)
        assertTrue(jpgFull.contains("record_end=50.0"))
    }

    @Test
    fun testRecordingRulesEndpoints() {
        assertEquals("/api/dvr/recording-rules", APIEndpoints.recordingRules())
        assertEquals("/api/dvr/recording-rules/rule_456", APIEndpoints.updateRecordingRule("rule_456"))
        assertEquals("/api/dvr/recording-rules/rule_456", APIEndpoints.deleteRecordingRule("rule_456"))
    }

    @Test
    fun testStreamingAndWatchEndpoints() {
        assertEquals("/api/streaming/hls/5.1", APIEndpoints.hlsChannelSession("5.1"))
        assertEquals("/api/streaming/hls/5.1?for_cast=true", APIEndpoints.hlsChannelSession("5.1", forCast = true))
        assertEquals("/api/streaming/hls/5.1?audio_index=2", APIEndpoints.hlsChannelSession("5.1", audioIndex = 2))
        assertEquals(
            "/api/streaming/hls/5.1?for_cast=true&audio_index=2",
            APIEndpoints.hlsChannelSession("5.1", forCast = true, audioIndex = 2)
        )

        assertEquals("/api/dvr/recording-stream-hls", APIEndpoints.hlsRecordingSession())
        assertEquals("/api/hls/sess_123/stop", APIEndpoints.stopHLSSession("sess_123"))

        assertEquals("/api/watch/5.1/start", APIEndpoints.startWatch("5.1"))
        assertEquals("/api/watch/sess_123/heartbeat", APIEndpoints.heartbeatWatch("sess_123"))
        assertEquals("/api/watch/sess_123/stop", APIEndpoints.stopWatch("sess_123"))
        assertEquals("/api/watch/sess_123/promote", APIEndpoints.promoteWatch("sess_123"))
    }

    @Test
    fun testTunerAndUserEndpoints() {
        assertEquals("/api/tuner/status", APIEndpoints.tunerStatus())
        assertEquals("/api/tuner/info", APIEndpoints.tunerInfo())

        assertEquals("/api/users", APIEndpoints.users())
        assertEquals("/api/users/user_1/login", APIEndpoints.loginUser("user_1"))
        assertEquals("/api/users/logout", APIEndpoints.logoutUser())
        assertEquals("/api/users/me", APIEndpoints.currentUser())
        assertEquals("/api/users/me/preferences", APIEndpoints.userPreferences())
    }

    @Test
    fun testDeviceAndSettingsEndpoints() {
        assertEquals("/api/devices/register", APIEndpoints.registerDevice())
        assertEquals("/api/devices/me", APIEndpoints.currentDevice())
        assertEquals("/api/devices", APIEndpoints.listDevices())
        assertEquals("/api/devices/dev_1", APIEndpoints.deleteDevice("dev_1"))

        assertEquals("/api/setup/status", APIEndpoints.setupStatus())
        assertEquals("/api/setup/admin", APIEndpoints.createSetupAdmin())

        assertEquals("/api/settings", APIEndpoints.settings())
        assertEquals("/api/streaming/transcode-presets", APIEndpoints.transcodePresets())
        assertEquals("/api/streaming/hwaccel-diagnostics", APIEndpoints.hwaccelDiagnostics())

        assertEquals("/api/network-settings", APIEndpoints.networkIntegrations())
        assertEquals("/api/network-settings/hdhomerun", APIEndpoints.networkIntegration("hdhomerun"))
        assertEquals("/api/network-settings/hdhomerun/test-tuner-connection", APIEndpoints.testTunerConnection())
        assertEquals("/api/network-settings/hdhomerun/test-dvr-connection", APIEndpoints.testDvrConnection())
    }

    @Test
    fun testSyncPlayEndpoints() {
        assertEquals("/api/syncplay/rooms", APIEndpoints.syncPlayRooms())
        assertEquals("/api/syncplay/rooms/ROOM12", APIEndpoints.syncPlayRoom("ROOM12"))

        assertEquals("/api/syncplay/ws/ROOM12", APIEndpoints.syncPlayWs("ROOM12"))
        val wsToken = APIEndpoints.syncPlayWs("ROOM12", token = "secret_tok")
        assertEquals("/api/syncplay/ws/ROOM12?token=secret_tok", wsToken)

        val wsBoth = APIEndpoints.syncPlayWs("ROOM12", token = "tok", userName = "Alice Bob")
        assertEquals("/api/syncplay/ws/ROOM12?token=tok&user_name=Alice+Bob", wsBoth)
    }

    @Test
    fun testAIAssistantEndpoints() {
        assertEquals("/api/ai/chat", APIEndpoints.aiChat())
        assertEquals("/api/ai/test-connection", APIEndpoints.aiTestConnection())
        assertEquals("/api/ai/list-models", APIEndpoints.aiListModels())
        assertEquals("/api/ai/actions/act_99/confirm", APIEndpoints.aiConfirmAction("act_99"))
        assertEquals("/api/ai/actions/act_99/cancel", APIEndpoints.aiCancelAction("act_99"))
    }
}
