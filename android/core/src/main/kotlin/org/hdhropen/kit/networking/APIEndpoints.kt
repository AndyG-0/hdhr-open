package org.hdhropen.kit.networking

import java.net.URLEncoder

object APIEndpoints {
    fun guideChannels(): String = "/api/guide/channels"
    fun guide(): String = "/api/guide"
    fun refreshGuide(): String = "/api/guide/refresh"

    fun dvrInfo(): String = "/api/dvr/info"
    fun recordings(): String = "/api/dvr/recordings"
    fun deleteRecording(id: String): String = "/api/dvr/recordings/$id"

    fun recordingDetail(url: String, recordingId: String, start: Double? = null, recordEnd: Double? = null): String {
        val query = mutableListOf<String>()
        query.add("url=${URLEncoder.encode(url, "UTF-8")}")
        query.add("recording_id=$recordingId")
        if (start != null) query.add("start=$start")
        if (recordEnd != null) query.add("record_end=$recordEnd")
        return "/api/dvr/recording-detail?${query.joinToString("&")}"
    }

    fun recordingCaptions(url: String, recordingId: String, recordEnd: Double? = null): String {
        val query = mutableListOf<String>()
        query.add("url=${URLEncoder.encode(url, "UTF-8")}")
        query.add("recording_id=$recordingId")
        if (recordEnd != null) query.add("record_end=$recordEnd")
        return "/api/dvr/recording-captions.vtt?${query.joinToString("&")}"
    }

    fun recordingThumbnailsVtt(url: String, recordingId: String, recordEnd: Double? = null): String {
        val query = mutableListOf<String>()
        query.add("url=${URLEncoder.encode(url, "UTF-8")}")
        if (recordEnd != null) query.add("record_end=$recordEnd")
        return "/api/dvr/recording-thumbnails/$recordingId.vtt?${query.joinToString("&")}"
    }

    fun recordingThumbnailsJpg(url: String, recordingId: String, recordEnd: Double? = null): String {
        val query = mutableListOf<String>()
        query.add("url=${URLEncoder.encode(url, "UTF-8")}")
        if (recordEnd != null) query.add("record_end=$recordEnd")
        return "/api/dvr/recording-thumbnails/$recordingId.jpg?${query.joinToString("&")}"
    }

    fun recordingRules(): String = "/api/dvr/recording-rules"
    fun deleteRecordingRule(id: String): String = "/api/dvr/recording-rules/$id"

    fun hlsChannelSession(channelNumber: String): String = "/api/streaming/hls/$channelNumber"
    fun hlsRecordingSession(): String = "/api/dvr/recording-stream-hls"
    fun stopHLSSession(sessionId: String): String = "/api/hls/$sessionId/stop"

    fun startWatch(channelNumber: String): String = "/api/watch/$channelNumber/start"
    fun heartbeatWatch(sessionId: String): String = "/api/watch/$sessionId/heartbeat"
    fun stopWatch(sessionId: String): String = "/api/watch/$sessionId/stop"
    fun promoteWatch(sessionId: String): String = "/api/watch/$sessionId/promote"

    fun tunerStatus(): String = "/api/tuner/status"
    fun tunerInfo(): String = "/api/tuner/info"

    fun users(): String = "/api/users"
    fun loginUser(id: String): String = "/api/users/$id/login"
    fun logoutUser(): String = "/api/users/logout"
    fun currentUser(): String = "/api/users/me"
    fun userPreferences(): String = "/api/users/me/preferences"

    fun registerDevice(): String = "/api/devices/register"
    fun currentDevice(): String = "/api/devices/me"
    fun listDevices(): String = "/api/devices"
    fun deleteDevice(id: String): String = "/api/devices/$id"

    fun setupStatus(): String = "/api/setup/status"
    fun createSetupAdmin(): String = "/api/setup/admin"

    fun settings(): String = "/api/settings"
    fun transcodePresets(): String = "/api/streaming/transcode-presets"
    fun hwaccelDiagnostics(): String = "/api/streaming/hwaccel-diagnostics"

    fun networkIntegrations(): String = "/api/network-settings"
    fun networkIntegration(type: String): String = "/api/network-settings/$type"
    fun testTunerConnection(): String = "/api/network-settings/hdhomerun/test-tuner-connection"
    fun testDvrConnection(): String = "/api/network-settings/hdhomerun/test-dvr-connection"
}
