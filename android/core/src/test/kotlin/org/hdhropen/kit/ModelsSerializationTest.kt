package org.hdhropen.kit

import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import org.hdhropen.kit.models.*
import org.junit.Assert.*
import org.junit.Test

class ModelsSerializationTest {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        coerceInputValues = true
    }

    @Test
    fun testDecodeChannel() {
        val jsonString = """
        {
            "channel_number": "5.1",
            "name": "KING-DT",
            "is_hd": true,
            "is_drm": false,
            "stream_url": "http://192.168.1.50:5004/auto/v5.1",
            "playback_url": "/api/streaming/stream/5.1",
            "now": {
                "title": "Evening News",
                "start": 1700000000.0,
                "end": 1700003600.0
            },
            "next": null
        }
        """.trimIndent()

        val channel = json.decodeFromString<HDHomeRunChannel>(jsonString)
        assertEquals("5.1", channel.channelNumber)
        assertEquals("KING-DT", channel.name)
        assertTrue(channel.isHD)
        assertFalse(channel.isDRM)
        assertEquals("Evening News", channel.now?.title)
        assertEquals("5.1", channel.id)
    }

    @Test
    fun testDecodeGuideEntry() {
        val jsonString = """
        {
            "series_id": "SH123",
            "title": "Quantum Odyssey",
            "episode_title": "Into the Void",
            "season_number": 3,
            "episode_number": "7",
            "synopsis": "An epic exploration into deep space.",
            "start": 1700000000.0,
            "end": 1700003600.0,
            "original_airdate": "2023-11-14",
            "image_url": "http://example.com/img.jpg",
            "channel_number": "4.1",
            "category": "Sci-Fi, Adventure",
            "is_new": true,
            "has_cc": true,
            "audio": "stereo"
        }
        """.trimIndent()

        val entry = json.decodeFromString<HDHomeRunGuideEntry>(jsonString)
        assertEquals("Quantum Odyssey", entry.title)
        assertEquals("Into the Void", entry.episodeTitle)
        assertEquals(3, entry.seasonNumber)
        assertEquals("S3E7", entry.formattedEpisodeDesignation)
        assertEquals("Sci-Fi, Adventure", entry.category)
        assertEquals(true, entry.isNew)
        assertEquals(true, entry.hasCC)
        assertEquals("STEREO", entry.formattedAudio)
    }

    @Test
    fun testDecodeRecording() {
        val jsonString = """
        {
            "recording_id": "rec_999",
            "title": "Cosmos: A Spacetime Odyssey",
            "episode_title": "Standing Up in the Milky Way",
            "season_number": 1,
            "episode_number": "1",
            "start": 1700000000.0,
            "record_end": 1700003600.0,
            "play_url": "/api/dvr/rec_999.mpg",
            "duration_seconds": 3600.0,
            "file_size_bytes": 4500000000
        }
        """.trimIndent()

        val rec = json.decodeFromString<HDHomeRunRecording>(jsonString)
        assertEquals("rec_999", rec.recordingId)
        assertEquals("Cosmos: A Spacetime Odyssey", rec.title)
        assertEquals("S1:E1", rec.episodeDesignation)
        assertEquals("1h 0m", rec.formattedDuration)
        assertTrue(rec.formattedFileSize.contains("GB"))
    }

    @Test
    fun testDecodeRecordingRule() {
        val jsonString = """
        {
            "RecordingRuleID": "rule_123",
            "SeriesID": "series_abc",
            "Title": "Star Trek",
            "Synopsis": "Sci-Fi Series",
            "ChannelOnly": "4.1",
            "DateTimeOnly": null,
            "StartPadding": 30,
            "EndPadding": 60,
            "RecentOnly": 1,
            "MaxEpisodesToKeep": 5
        }
        """.trimIndent()

        val rule = json.decodeFromString<HDHomeRunRecordingRule>(jsonString)
        assertEquals("rule_123", rule.recordingRuleId)
        assertEquals("series_abc", rule.seriesId)
        assertEquals("Star Trek", rule.title)
        assertEquals("4.1", rule.channelOnly)
        assertTrue(rule.isSeriesRule)
        assertFalse(rule.isEpisodeRule)
        assertEquals(30, rule.startPadding)
    }

    @Test
    fun testDecodeTunerStatus() {
        val jsonString = """
        {
            "index": 0,
            "in_use": true,
            "channel_number": "9.1",
            "channel_name": "KCTS",
            "signal_strength_percent": 95,
            "signal_quality_percent": 100,
            "symbol_quality_percent": 100,
            "network_rate_bps": 15000000
        }
        """.trimIndent()

        val tuner = json.decodeFromString<HDHomeRunTuner>(jsonString)
        assertEquals(0, tuner.index)
        assertTrue(tuner.inUse)
        assertEquals("9.1", tuner.channelNumber)
        assertEquals("15.0 Mbps", tuner.formattedRateMbps)
    }

    @Test
    fun testDecodeUserProfile() {
        val jsonString = """
        {
            "id": "user_1",
            "name": "Andy",
            "avatar": "avatar_1.png",
            "has_pin": true
        }
        """.trimIndent()

        val profile = json.decodeFromString<UserProfile>(jsonString)
        assertEquals("user_1", profile.id)
        assertEquals("Andy", profile.name)
        assertTrue(profile.hasPin)
    }

    @Test
    fun testDecodeHouseholdUserAndCurrentUser() {
        val householdJson = """
        {
            "id": "h_user_1",
            "name": "Sarah",
            "avatar": "avatar_2.png",
            "has_pin": false,
            "role": "admin",
            "created_at": "2026-09-01T00:00:00Z"
        }
        """.trimIndent()

        val hUser = json.decodeFromString<HouseholdUser>(householdJson)
        assertEquals("h_user_1", hUser.id)
        assertEquals("Sarah", hUser.name)
        assertEquals(UserRole.ADMIN, hUser.role)
        assertEquals("2026-09-01T00:00:00Z", hUser.createdAt)

        val currentJson = """
        {
            "id": "curr_1",
            "name": "Admin User",
            "role": "admin",
            "token": "secret_jwt"
        }
        """.trimIndent()

        val curr = json.decodeFromString<CurrentUser>(currentJson)
        assertEquals("curr_1", curr.id)
        assertTrue(curr.isAdmin)
        assertEquals("secret_jwt", curr.token)

        val memberJson = """{"id": "m1", "name": "Member", "role": "member"}"""
        val member = json.decodeFromString<CurrentUser>(memberJson)
        assertFalse(member.isAdmin)

        val setup = json.decodeFromString<SetupStatus>("""{"needs_setup": true}""")
        assertTrue(setup.needsSetup)

        val prefs = json.decodeFromString<UserPreferences>("""{"theme": "dark", "locale": "en-US"}""")
        assertEquals("dark", prefs.theme)
        assertEquals("en-US", prefs.locale)
    }
}
