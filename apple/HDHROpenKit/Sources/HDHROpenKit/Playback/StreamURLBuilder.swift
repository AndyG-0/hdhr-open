import Foundation

public enum StreamURLBuilder {
    public static func liveStreamURL(baseURL: URL, channelNumber: String) -> URL? {
        URL(string: "/api/streaming/stream/\(channelNumber)", relativeTo: baseURL)?.absoluteURL
    }

    public static func recordingStreamURL(
        baseURL: URL,
        playUrl: String,
        recordingId: String? = nil,
        startOffset: Double? = nil,
        audioIndex: Int? = nil
    ) -> URL? {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "url", value: playUrl)
        ]
        if let recId = recordingId {
            queryItems.append(URLQueryItem(name: "recording_id", value: recId))
        }
        if let start = startOffset, start > 0 {
            queryItems.append(URLQueryItem(name: "start", value: String(format: "%.1f", start)))
        }
        if let audio = audioIndex {
            queryItems.append(URLQueryItem(name: "audio_index", value: String(audio)))
        }

        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: true)
        components?.path = "/api/dvr/recording-stream"
        components?.queryItems = queryItems
        return components?.url
    }

    public static func hlsPlaylistURL(baseURL: URL, sessionId: String) -> URL? {
        URL(string: "/api/hls/\(sessionId)/playlist.m3u8", relativeTo: baseURL)?.absoluteURL
    }

    public static func thumbnailSpriteURL(baseURL: URL, recordingId: String, playUrl: String, recordEnd: Double? = nil) -> URL? {
        var queryItems = [URLQueryItem(name: "url", value: playUrl)]
        if let end = recordEnd {
            queryItems.append(URLQueryItem(name: "record_end", value: String(format: "%.1f", end)))
        }
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: true)
        components?.path = "/api/dvr/recording-thumbnails/\(recordingId).jpg"
        components?.queryItems = queryItems
        return components?.url
    }

    public static func thumbnailVttURL(baseURL: URL, recordingId: String, playUrl: String, recordEnd: Double? = nil) -> URL? {
        var queryItems = [URLQueryItem(name: "url", value: playUrl)]
        if let end = recordEnd {
            queryItems.append(URLQueryItem(name: "record_end", value: String(format: "%.1f", end)))
        }
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: true)
        components?.path = "/api/dvr/recording-thumbnails/\(recordingId).vtt"
        components?.queryItems = queryItems
        return components?.url
    }

    public static func captionsURL(baseURL: URL, recordingId: String, playUrl: String, recordEnd: Double? = nil) -> URL? {
        var queryItems = [
            URLQueryItem(name: "url", value: playUrl),
            URLQueryItem(name: "recording_id", value: recordingId)
        ]
        if let end = recordEnd {
            queryItems.append(URLQueryItem(name: "record_end", value: String(format: "%.1f", end)))
        }
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: true)
        components?.path = "/api/dvr/recording-captions.vtt"
        components?.queryItems = queryItems
        return components?.url
    }
}
