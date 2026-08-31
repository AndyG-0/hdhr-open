package org.hdhropen.kit.playback

import java.net.URLEncoder

object StreamURLBuilder {
    fun liveStreamURL(baseURL: String, channelNumber: String, direct: Boolean = false): String {
        val base = baseURL.trimEnd('/')
        val query = if (direct) "?direct=true" else ""
        return "$base/api/streaming/stream/$channelNumber$query"
    }

    fun recordingStreamURL(
        baseURL: String,
        playUrl: String,
        recordingId: String? = null,
        startOffset: Double? = null,
        audioIndex: Int? = null,
        provider: String? = null
    ): String {
        val base = baseURL.trimEnd('/')
        val queryItems = mutableListOf<String>()
        queryItems.add("url=${URLEncoder.encode(playUrl, "UTF-8")}")
        if (recordingId != null) {
            queryItems.add("recording_id=$recordingId")
        }
        if (startOffset != null && startOffset > 0) {
            queryItems.add("start=${String.format(java.util.Locale.US, "%.1f", startOffset)}")
        }
        if (audioIndex != null) {
            queryItems.add("audio_index=$audioIndex")
        }
        if (provider != null) {
            queryItems.add("provider=$provider")
        }
        return "$base/api/dvr/recording-stream?${queryItems.joinToString("&")}"
    }

    fun hlsPlaylistURL(baseURL: String, sessionId: String): String {
        val base = baseURL.trimEnd('/')
        return "$base/api/hls/$sessionId/playlist.m3u8"
    }

    fun thumbnailSpriteURL(
        baseURL: String,
        recordingId: String,
        playUrl: String,
        recordEnd: Double? = null,
        provider: String? = null
    ): String {
        val base = baseURL.trimEnd('/')
        val query = mutableListOf<String>()
        query.add("url=${URLEncoder.encode(playUrl, "UTF-8")}")
        if (recordEnd != null) {
            query.add("record_end=${String.format(java.util.Locale.US, "%.1f", recordEnd)}")
        }
        if (provider != null) {
            query.add("provider=$provider")
        }
        return "$base/api/dvr/recording-thumbnails/$recordingId.jpg?${query.joinToString("&")}"
    }

    fun thumbnailVttURL(
        baseURL: String,
        recordingId: String,
        playUrl: String,
        recordEnd: Double? = null,
        provider: String? = null
    ): String {
        val base = baseURL.trimEnd('/')
        val query = mutableListOf<String>()
        query.add("url=${URLEncoder.encode(playUrl, "UTF-8")}")
        if (recordEnd != null) {
            query.add("record_end=${String.format(java.util.Locale.US, "%.1f", recordEnd)}")
        }
        if (provider != null) {
            query.add("provider=$provider")
        }
        return "$base/api/dvr/recording-thumbnails/$recordingId.vtt?${query.joinToString("&")}"
    }

    fun captionsURL(
        baseURL: String,
        recordingId: String,
        playUrl: String,
        recordEnd: Double? = null,
        provider: String? = null
    ): String {
        val base = baseURL.trimEnd('/')
        val query = mutableListOf<String>()
        query.add("url=${URLEncoder.encode(playUrl, "UTF-8")}")
        query.add("recording_id=$recordingId")
        if (recordEnd != null) {
            query.add("record_end=${String.format(java.util.Locale.US, "%.1f", recordEnd)}")
        }
        if (provider != null) {
            query.add("provider=$provider")
        }
        return "$base/api/dvr/recording-captions.vtt?${query.joinToString("&")}"
    }
}
