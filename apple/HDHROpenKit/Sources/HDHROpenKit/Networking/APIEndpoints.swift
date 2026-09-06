import Foundation

public enum APIEndpoints {
    public static func guideChannels() -> String { "/api/guide/channels" }
    public static func guide(start: Double? = nil, end: Double? = nil) -> String {
        var query: [String] = []
        if let s = start { query.append("start=\(s)") }
        if let e = end { query.append("end=\(e)") }
        return query.isEmpty ? "/api/guide" : "/api/guide?\(query.joined(separator: "&"))"
    }
    public static func refreshGuide() -> String { "/api/guide/refresh" }

    public static func dvrInfo() -> String { "/api/dvr/info" }
    public static func recordings() -> String { "/api/dvr/recordings" }
    public static func deleteRecording(_ id: String) -> String { "/api/dvr/recordings/\(id)" }
    public static func recordingDetail(url: String, recordingId: String, start: Double? = nil, recordEnd: Double? = nil) -> String {
        var query: [String] = [
            "url=\(url.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? url)",
            "recording_id=\(recordingId)"
        ]
        if let s = start { query.append("start=\(s)") }
        if let e = recordEnd { query.append("record_end=\(e)") }
        return "/api/dvr/recording-detail?\(query.joined(separator: "&"))"
    }
    public static func recordingCaptions(url: String, recordingId: String, recordEnd: Double? = nil) -> String {
        var query: [String] = [
            "url=\(url.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? url)",
            "recording_id=\(recordingId)"
        ]
        if let e = recordEnd { query.append("record_end=\(e)") }
        return "/api/dvr/recording-captions.vtt?\(query.joined(separator: "&"))"
    }
    public static func recordingThumbnailsVtt(url: String, recordingId: String, recordEnd: Double? = nil) -> String {
        var query: [String] = ["url=\(url.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? url)"]
        if let e = recordEnd { query.append("record_end=\(e)") }
        return "/api/dvr/recording-thumbnails/\(recordingId).vtt?\(query.joined(separator: "&"))"
    }
    public static func recordingThumbnailsJpg(url: String, recordingId: String, recordEnd: Double? = nil) -> String {
        var query: [String] = ["url=\(url.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? url)"]
        if let e = recordEnd { query.append("record_end=\(e)") }
        return "/api/dvr/recording-thumbnails/\(recordingId).jpg?\(query.joined(separator: "&"))"
    }

    public static func recordingRules() -> String { "/api/dvr/recording-rules" }
    public static func updateRecordingRule(_ id: String) -> String { "/api/dvr/recording-rules/\(id)" }
    public static func deleteRecordingRule(_ id: String) -> String { "/api/dvr/recording-rules/\(id)" }

    public static func hlsChannelSession(channelNumber: String, audioIndex: Int? = nil) -> String {
        if let audio = audioIndex {
            return "/api/streaming/hls/\(channelNumber)?audio_index=\(audio)"
        }
        return "/api/streaming/hls/\(channelNumber)"
    }
    public static func hlsRecordingSession() -> String { "/api/dvr/recording-stream-hls" }
    public static func stopHLSSession(sessionId: String) -> String { "/api/hls/\(sessionId)/stop" }

    public static func startWatch(channelNumber: String) -> String { "/api/watch/\(channelNumber)/start" }
    public static func heartbeatWatch(sessionId: String) -> String { "/api/watch/\(sessionId)/heartbeat" }
    public static func stopWatch(sessionId: String) -> String { "/api/watch/\(sessionId)/stop" }
    public static func promoteWatch(sessionId: String) -> String { "/api/watch/\(sessionId)/promote" }

    public static func tunerStatus() -> String { "/api/tuner/status" }
    public static func tunerInfo() -> String { "/api/tuner/info" }

    public static func users() -> String { "/api/users" }
    public static func loginUser(_ id: String) -> String { "/api/users/\(id)/login" }
    public static func logoutUser() -> String { "/api/users/logout" }
    public static func currentUser() -> String { "/api/users/me" }
    public static func userPreferences() -> String { "/api/users/me/preferences" }

    public static func registerDevice() -> String { "/api/devices/register" }
    public static func currentDevice() -> String { "/api/devices/me" }
    public static func listDevices() -> String { "/api/devices" }
    public static func deleteDevice(_ id: String) -> String { "/api/devices/\(id)" }

    public static func setupStatus() -> String { "/api/setup/status" }
    public static func createSetupAdmin() -> String { "/api/setup/admin" }

    public static func settings() -> String { "/api/settings" }
    public static func transcodePresets() -> String { "/api/streaming/transcode-presets" }
    public static func hwaccelDiagnostics() -> String { "/api/streaming/hwaccel-diagnostics" }

    public static func networkIntegrations() -> String { "/api/network-settings" }
    public static func networkIntegration(_ type: String) -> String { "/api/network-settings/\(type)" }
    public static func testTunerConnection() -> String { "/api/network-settings/hdhomerun/test-tuner-connection" }
    public static func testDvrConnection() -> String { "/api/network-settings/hdhomerun/test-dvr-connection" }

    public static func syncPlayRooms() -> String { "/api/syncplay/rooms" }
    public static func syncPlayRoom(_ code: String) -> String { "/api/syncplay/rooms/\(code)" }
    public static func syncPlayWs(roomCode: String, userName: String? = nil, token: String? = nil) -> String {
        var query: [String] = []
        if let token = token {
            query.append("token=\(token.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? token)")
        }
        if let userName = userName {
            query.append("user_name=\(userName.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? userName)")
        }
        let q = query.isEmpty ? "" : "?\(query.joined(separator: "&"))"
        return "/api/syncplay/ws/\(roomCode)\(q)"
    }

    // MARK: - AI Assistant APIs

    public static func aiChat() -> String { "/api/ai/chat" }
    public static func aiTestConnection() -> String { "/api/ai/test-connection" }
    public static func aiListModels() -> String { "/api/ai/list-models" }
    public static func aiConfirmAction(_ id: String) -> String { "/api/ai/actions/\(id)/confirm" }
    public static func aiCancelAction(_ id: String) -> String { "/api/ai/actions/\(id)/cancel" }
}

