package org.hdhropen.kit

import kotlinx.serialization.json.JsonPrimitive
import org.hdhropen.kit.models.*
import org.hdhropen.kit.playback.PlaybackPreferences
import org.hdhropen.kit.theme.ThemeMode
import org.hdhropen.kit.theme.ThemePreferences
import org.hdhropen.kit.utilities.Log
import org.hdhropen.kit.utilities.TimeFormatting
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.util.Calendar

@RunWith(RobolectricTestRunner::class)
class UtilitiesAndPreferencesTest {

    // MARK: - TimeFormatting Tests

    @Test
    fun testTimeFormatting_formatTimeAndRanges() {
        val nowSec = 1700000000.0 // Fixed epoch timestamp
        val timeStr = TimeFormatting.formatTime(nowSec)
        assertTrue(timeStr.isNotEmpty())

        assertEquals("", TimeFormatting.formatTime(null))

        // Time range variations
        assertEquals("", TimeFormatting.formatTimeRange(null, null))
        assertEquals(timeStr, TimeFormatting.formatTimeRange(nowSec, null))
        assertTrue(TimeFormatting.formatTimeRange(null, nowSec + 3600).startsWith("Until "))

        val rangeStr = TimeFormatting.formatTimeRange(nowSec, nowSec + 3600)
        assertTrue(rangeStr.contains("–") || rangeStr.contains("-"))
    }

    @Test
    fun testTimeFormatting_dayLabelAndHour() {
        val nowSec = System.currentTimeMillis() / 1000.0
        assertEquals("Today", TimeFormatting.formatDayLabel(nowSec))

        val tomorrowSec = nowSec + 86400.0
        assertEquals("Tomorrow", TimeFormatting.formatDayLabel(tomorrowSec))

        val pastSec = nowSec - 86400.0 * 5
        val weekday = TimeFormatting.formatDayLabel(pastSec)
        assertFalse(weekday == "Today" || weekday == "Tomorrow")

        val hour = TimeFormatting.formatHour(nowSec)
        assertTrue(hour.isNotEmpty())

        val fullDate = TimeFormatting.formatFullDate(nowSec)
        assertTrue(fullDate.isNotEmpty())
    }

    @Test
    fun testTimeFormatting_durationAndClock() {
        assertEquals("", TimeFormatting.formatDuration(null))
        assertEquals("", TimeFormatting.formatDuration(-10.0))
        assertEquals("30m", TimeFormatting.formatDuration(1800.0))
        assertEquals("1h 15m", TimeFormatting.formatDuration(4500.0))

        assertEquals("0:45", TimeFormatting.formatSecondsToClock(45.0))
        assertEquals("5:30", TimeFormatting.formatSecondsToClock(330.0))
        assertEquals("1:05:00", TimeFormatting.formatSecondsToClock(3900.0))
    }

    // MARK: - Preferences Tests

    @Test
    fun testThemePreferences_inMemory() {
        val prefs = ThemePreferences(context = null)
        assertEquals(ThemeMode.SYSTEM, prefs.themeMode.value)

        prefs.setThemeMode(ThemeMode.DARK)
        assertEquals(ThemeMode.DARK, prefs.themeMode.value)

        prefs.setThemeMode(ThemeMode.LIGHT)
        assertEquals(ThemeMode.LIGHT, prefs.themeMode.value)
    }

    @Test
    fun testPlaybackPreferences_inMemory() {
        val prefs = PlaybackPreferences(context = null)
        assertFalse(prefs.directPlayEnabled.value)

        prefs.setDirectPlayEnabled(true)
        assertTrue(prefs.directPlayEnabled.value)
    }

    // MARK: - Logger Test

    @Test
    fun testLogger_allChannels() {
        Log.general.info("Info message")
        Log.general.debug("Debug message")
        Log.general.warning("Warning message")
        Log.general.error("Error message")

        Log.player.info("Player info")
        Log.network.info("Network info")
        Log.dvr.info("DVR info")
        Log.auth.info("Auth info")
    }

    // MARK: - Models Computed Properties & Helpers

    @Test
    fun testGuideEntryHelpers() {
        val entry = HDHomeRunGuideEntry(
            seriesId = "s123",
            title = "Awesome Show",
            start = 1000.0,
            end = 2000.0,
            channelNumber = "4.1",
            seasonNumber = 2,
            episodeNumber = "5",
            audio = "5.1 Surround"
        )
        assertEquals("s123_1000_4.1", entry.id)
        assertEquals(1000.0, entry.durationSeconds)
        assertEquals("S2E5", entry.formattedEpisodeDesignation)
        assertEquals("5.1", entry.formattedAudio)

        // Episode format variations
        val epOnly = HDHomeRunGuideEntry(title = "Movie", episodeNumber = "12")
        assertEquals("Ep 12", epOnly.formattedEpisodeDesignation)

        val dotEp = HDHomeRunGuideEntry(title = "Show", episodeNumber = "3.4")
        assertEquals("S3E4", dotEp.formattedEpisodeDesignation)

        val seasonDotEp = HDHomeRunGuideEntry(title = "Show", seasonNumber = 2, episodeNumber = "2.5")
        assertEquals("S2E5", seasonDotEp.formattedEpisodeDesignation)

        val noEp = HDHomeRunGuideEntry(title = "Movie")
        assertNull(noEp.formattedEpisodeDesignation)

        // Audio format variations
        val stereoEntry = HDHomeRunGuideEntry(title = "Show", audio = "stereo")
        assertEquals("STEREO", stereoEntry.formattedAudio)

        val dolbyEntry = HDHomeRunGuideEntry(title = "Show", audio = "Dolby Digital")
        assertEquals("DOLBY", dolbyEntry.formattedAudio)

        val ddEntry = HDHomeRunGuideEntry(title = "Show", audio = "DD+")
        assertEquals("DOLBY", ddEntry.formattedAudio)

        val monoEntry = HDHomeRunGuideEntry(title = "Show", audio = "mono")
        assertEquals("MONO", monoEntry.formattedAudio)

        val otherAudio = HDHomeRunGuideEntry(title = "Show", audio = "dts")
        assertEquals("DTS", otherAudio.formattedAudio)

        val nullAudio = HDHomeRunGuideEntry(title = "Show", audio = null)
        assertNull(nullAudio.formattedAudio)

        // ID variations
        val noSeriesEntry = HDHomeRunGuideEntry(title = "Show", start = 1000.0, channelNumber = "2.1")
        assertEquals("Show_1000_2.1", noSeriesEntry.id)

        val noStartEntry = HDHomeRunGuideEntry(title = "Show")
        assertEquals("Show_0_", noStartEntry.id)

        // Duration variations
        val invalidDur = HDHomeRunGuideEntry(title = "Show", start = 1000.0, end = 500.0)
        assertNull(invalidDur.durationSeconds)

        // Airing and progress checks
        assertTrue(entry.isCurrentlyAiring(1500.0))
        assertFalse(entry.isCurrentlyAiring(500.0))
        assertFalse(entry.isCurrentlyAiring(2500.0))
        assertFalse(noStartEntry.isCurrentlyAiring())

        assertEquals(0.5f, entry.progress(1500.0), 0.01f)
        assertEquals(0f, entry.progress(500.0), 0.01f)
        assertEquals(1f, entry.progress(2500.0), 0.01f)
        assertEquals(0f, invalidDur.progress(1000.0), 0.01f)
        assertEquals(0f, noStartEntry.progress(), 0.01f)
    }

    @Test
    fun testRecordingHelpers() {
        val rec = HDHomeRunRecording(
            title = "News",
            recordingId = "rec-1",
            durationSeconds = 3660.0,
            fileSizeBytes = 2_147_483_648L, // 2 GB
            seasonNumber = 1,
            episodeNumber = "02"
        )
        assertEquals("rec-1", rec.id)
        assertEquals("1h 1m", rec.formattedDuration)
        assertEquals("S1:E02", rec.episodeDesignation)
        assertEquals("2.0 GB", rec.formattedFileSize)

        val mbRec = HDHomeRunRecording(title = "Clip", fileSizeBytes = 52_428_800L) // 50 MB
        assertEquals("50 MB", mbRec.formattedFileSize)

        val emptyRec = HDHomeRunRecording(title = "Empty")
        assertEquals("", emptyRec.formattedDuration)
        assertEquals("", emptyRec.formattedFileSize)
        assertNull(emptyRec.episodeDesignation)
        assertFalse(emptyRec.isInProgress)

        val shortRec = HDHomeRunRecording(title = "Short", durationSeconds = 90.0, episodeNumber = "5")
        assertEquals("1m", shortRec.formattedDuration)
        assertEquals("Ep 5", shortRec.episodeDesignation)

        val negRec = HDHomeRunRecording(title = "Negative", durationSeconds = -10.0, fileSizeBytes = -5L)
        assertEquals("", negRec.formattedDuration)
        assertEquals("", negRec.formattedFileSize)

        val playUrlRec = HDHomeRunRecording(title = "Stream", playUrl = "/api/stream/1")
        assertEquals("/api/stream/1", playUrlRec.id)

        val fallbackIdRec = HDHomeRunRecording(title = "TitleOnly", start = 500.0)
        assertEquals("TitleOnly_500", fallbackIdRec.id)
    }

    @Test
    fun testAudioInfoLabels() {
        val track1 = HDHomeRunRecordingAudioInfo(index = 0, title = "Commentary", channels = 2, codec = "aac")
        assertEquals("Commentary • Stereo • AAC", track1.displayLabel)

        val track2 = HDHomeRunRecordingAudioInfo(index = 1, language = "spa", channels = 6, codec = "ac3")
        assertEquals("SPA • 5.1 Surround • AC3", track2.displayLabel)

        val track3 = HDHomeRunRecordingAudioInfo(index = 2, channels = 1)
        assertEquals("Track 3 • 1 ch", track3.displayLabel)
    }

    @Test
    fun testTunerAndDvrInfoFormatting() {
        val tuner = HDHomeRunTuner(index = 0, networkRateBps = 15_500_000L)
        assertEquals("15.5 Mbps", tuner.formattedRateMbps)

        val idleTuner = HDHomeRunTuner(index = 1, networkRateBps = null)
        assertEquals("0.0 Mbps", idleTuner.formattedRateMbps)

        val gbDvr = HDHomeRunDvrInfo(freeSpaceBytes = 536_870_912_000L) // 500 GB
        assertEquals("500.0 GB free", gbDvr.formattedFreeSpace)

        val tbDvr = HDHomeRunDvrInfo(freeSpaceBytes = 2_199_023_255_552L) // 2 TB
        assertEquals("2.00 TB free", tbDvr.formattedFreeSpace)

        val unknownDvr = HDHomeRunDvrInfo(freeSpaceBytes = null)
        assertEquals("Unknown", unknownDvr.formattedFreeSpace)
    }

    @Test
    fun testAIChatHelpers_toWireMessages() {
        assertTrue(AIChatHelpers.quickSuggestions.isNotEmpty())

        val turns = listOf(
            AIChatTurn(role = "user", text = "What is on?"),
            AIChatTurn(
                role = "assistant",
                text = "Checking guide...",
                toolCalls = mutableListOf(
                    AIToolCallRecord(
                        id = "call-1",
                        name = "get_guide",
                        arguments = emptyMap(),
                        result = mapOf("status" to JsonPrimitive("ok"))
                    )
                )
            )
        )

        val wire = AIChatHelpers.toWireMessages(turns)
        assertEquals(3, wire.size)
        assertEquals("user", wire[0].role)
        assertEquals("assistant", wire[1].role)
        assertEquals(1, wire[1].toolCalls?.size)
        assertEquals("tool", wire[2].role)
        assertEquals("call-1", wire[2].toolCallId)
    }

    @Test
    fun testAppEnvironment() {
        val context = org.robolectric.RuntimeEnvironment.getApplication()
        val appEnv = org.hdhropen.kit.viewmodels.AppEnvironment(context, "http://10.0.0.1:8000")

        assertNotNull(appEnv.serverDiscovery)
        assertNotNull(appEnv.apiClient)
        assertNotNull(appEnv.authManager)
        assertNotNull(appEnv.watchSessionManager)
        assertNotNull(appEnv.playerEngine)
        assertNotNull(appEnv.playbackPreferences)
        assertNotNull(appEnv.themePreferences)

        assertNotNull(appEnv.guideViewModel)
        assertNotNull(appEnv.recordingsViewModel)
        assertNotNull(appEnv.playerViewModel)
        assertNotNull(appEnv.tunerViewModel)
        assertNotNull(appEnv.settingsViewModel)
        assertNotNull(appEnv.authViewModel)

        appEnv.updateServerURL("http://192.168.1.55:8000")
        assertEquals("http://192.168.1.55:8000", appEnv.serverDiscovery.serverURLString.value)
        assertEquals("http://192.168.1.55:8000", appEnv.apiClient.baseURL)
    }

    @Test
    fun testChannelSettingsAndDeviceInfoModels() {
        val setting = HDHomeRunChannelSetting(
            id = "ch-1",
            channelNumber = "7.1",
            name = "KIRO",
            isHD = true,
            isFavorite = true,
            hidden = false,
            guideProvider = "xmltv",
            xmltvChannelId = "kiro.tv",
            xmltvDisplayName = "KIRO 7",
            sdStationId = "12345",
            sdLineupId = "USA-OTA"
        )
        assertEquals("ch-1", setting.id)
        assertEquals("7.1", setting.channelNumber)
        assertTrue(setting.isHD)
        assertTrue(setting.isFavorite)
        assertFalse(setting.hidden)
        assertEquals("xmltv", setting.guideProvider)
        assertEquals("kiro.tv", setting.xmltvChannelId)

        val fullGuide = HDHomeRunFullGuideChannel(
            channelNumber = "7.1",
            channelName = "KIRO",
            airings = emptyList()
        )
        assertEquals("7.1", fullGuide.id)

        val devInfo = DeviceInfo(id = "d1", name = "Pixel 8")
        assertEquals("d1", devInfo.id)
        assertEquals("Pixel 8", devInfo.name)

        val devEntry = DeviceListEntry(id = "d2", name = "Shield TV", lastSeenAt = "2026-09-07T00:00:00Z")
        assertEquals("d2", devEntry.id)
        assertEquals("Shield TV", devEntry.name)

        val devResult = DeviceRegisterResult(id = "d3", name = "Tablet", isNew = true)
        assertEquals("d3", devResult.id)
        assertTrue(devResult.isNew)
    }

    @Test
    fun testTunerAndNetworkModels() {
        val viewer = TunerViewerInfo(userName = "Alice", clientIp = "192.168.1.20")
        assertEquals("Alice", viewer.userName)
        assertEquals("192.168.1.20", viewer.clientIp)

        val client = TunerClientInfo(
            type = "live",
            name = "Living Room",
            ip = "192.168.1.10",
            hostname = "tv.local",
            details = "Watching 5.1",
            recordingId = "rec1",
            scheduledId = "sch1",
            isRecording = true,
            viewers = listOf(viewer)
        )
        assertEquals("live", client.type)
        assertEquals("Living Room", client.name)
        assertTrue(client.isRecording)
        assertEquals(1, client.viewers.size)

        val warning = TunerWarningInfo(severity = "warning", message = "Weak signal")
        assertEquals("warning", warning.severity)
        assertEquals("Weak signal", warning.message)

        val appSettings = AppSettings(
            timezone = "America/Los_Angeles",
            guideProviderPriority = "xmltv",
            dvrServerPriority = "primary"
        )
        assertEquals("America/Los_Angeles", appSettings.timezone)
        assertEquals("xmltv", appSettings.guideProviderPriority)

        val preset = HDHomeRunTranscodePreset(
            id = "p1",
            label = "1080p",
            description = "High quality",
            inputArgs = listOf("-i"),
            outputArgs = listOf("-c:v", "libx264"),
            hardware = true
        )
        assertEquals("p1", preset.id)
        assertTrue(preset.hardware)

        val diag = HWAccelDiagnostics(device = "/dev/dri/renderD128", summary = listOf("VAAPI ready"), sampleError = null)
        assertEquals("/dev/dri/renderD128", diag.device)
        assertEquals(1, diag.summary.size)

        val netInt = NetworkIntegration(id = "hdhr1", type = "hdhomerun", name = "Local Tuners")
        assertEquals("hdhr1", netInt.id)

        val testConn = NetworkTestConnectionResult(ok = true, detail = "Connected")
        assertTrue(testConn.ok)
        assertEquals("Connected", testConn.detail)
    }
}
