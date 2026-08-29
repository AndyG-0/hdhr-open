package org.hdhropen.kit

import org.hdhropen.kit.playback.StreamURLBuilder
import org.junit.Assert.*
import org.junit.Test

class StreamURLBuilderTest {
    @Test
    fun testLiveStreamURL() {
        val base = "http://192.168.1.100:8000"
        val url = StreamURLBuilder.liveStreamURL(base, "4.1")
        assertEquals("http://192.168.1.100:8000/api/streaming/stream/4.1", url)
    }

    @Test
    fun testHLSPlaylistURL() {
        val base = "http://192.168.1.100:8000"
        val url = StreamURLBuilder.hlsPlaylistURL(base, "abc123")
        assertEquals("http://192.168.1.100:8000/api/hls/abc123/playlist.m3u8", url)
    }

    @Test
    fun testRecordingStreamURL() {
        val base = "http://192.168.1.100:8000"
        val url = StreamURLBuilder.recordingStreamURL(
            baseURL = base,
            playUrl = "http://hdhr/rec.mpg",
            recordingId = "rec_123",
            startOffset = 120.5,
            audioIndex = 1
        )
        assertNotNull(url)
        assertTrue(url.contains("recording_id=rec_123"))
        assertTrue(url.contains("start=120.5"))
        assertTrue(url.contains("audio_index=1"))
    }

    @Test
    fun testThumbnailAndCaptionsURL() {
        val base = "http://192.168.1.100:8000"
        val thumbJpg = StreamURLBuilder.thumbnailSpriteURL(base, "rec_123", "http://hdhr/rec.mpg", 1700003600.0)
        assertTrue(thumbJpg.contains("/api/dvr/recording-thumbnails/rec_123.jpg"))
        assertTrue(thumbJpg.contains("record_end=1700003600.0"))

        val captions = StreamURLBuilder.captionsURL(base, "rec_123", "http://hdhr/rec.mpg", 1700003600.0)
        assertTrue(captions.contains("/api/dvr/recording-captions.vtt"))
        assertTrue(captions.contains("recording_id=rec_123"))
    }
}
