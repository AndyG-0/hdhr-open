import Foundation

public struct HDHomeRunRecordingVideoInfo: Codable, Sendable, Hashable {
    public let codec: String?
    public let width: Int?
    public let height: Int?
    public let fps: Double?

    public init(codec: String? = nil, width: Int? = nil, height: Int? = nil, fps: Double? = nil) {
        self.codec = codec
        self.width = width
        self.height = height
        self.fps = fps
    }
}

public struct HDHomeRunRecordingAudioInfo: Identifiable, Codable, Sendable, Hashable {
    public var id: Int { index }
    public let index: Int
    public let codec: String?
    public let channels: Int?
    public let language: String?
    public let title: String?
    public let isDescriptive: Bool?
    public let isHearingImpaired: Bool?
    public let isCommentary: Bool?
    public let isDefault: Bool?

    enum CodingKeys: String, CodingKey {
        case index
        case codec
        case channels
        case language
        case title
        case isDescriptive = "is_descriptive"
        case isHearingImpaired = "is_hearing_impaired"
        case isCommentary = "is_commentary"
        case isDefault = "is_default"
    }

    public init(
        index: Int,
        codec: String? = nil,
        channels: Int? = nil,
        language: String? = nil,
        title: String? = nil,
        isDescriptive: Bool? = nil,
        isHearingImpaired: Bool? = nil,
        isCommentary: Bool? = nil,
        isDefault: Bool? = nil
    ) {
        self.index = index
        self.codec = codec
        self.channels = channels
        self.language = language
        self.title = title
        self.isDescriptive = isDescriptive
        self.isHearingImpaired = isHearingImpaired
        self.isCommentary = isCommentary
        self.isDefault = isDefault
    }

    public var displayLabel: String {
        var parts: [String] = []
        if let t = title, !t.isEmpty {
            parts.append(t)
        } else if let lang = language, !lang.isEmpty {
            parts.append(lang.uppercased())
        } else {
            parts.append("Track \(index + 1)")
        }
        if let ch = channels {
            if ch == 6 {
                parts.append("5.1 Surround")
            } else if ch == 2 {
                parts.append("Stereo")
            } else {
                parts.append("\(ch) ch")
            }
        }
        if let c = codec, !c.isEmpty {
            parts.append(c.uppercased())
        }
        return parts.joined(separator: " • ")
    }
}

public struct HDHomeRunTranscodeInfo: Codable, Sendable {
    public let transcoding: Bool
    public let preset: String?
    public let presetLabel: String?
    public let hardware: Bool

    enum CodingKeys: String, CodingKey {
        case transcoding
        case preset
        case presetLabel = "preset_label"
        case hardware
    }

    public init(transcoding: Bool, preset: String? = nil, presetLabel: String? = nil, hardware: Bool = false) {
        self.transcoding = transcoding
        self.preset = preset
        self.presetLabel = presetLabel
        self.hardware = hardware
    }
}

public struct HDHomeRunRecordingDetail: Codable, Sendable {
    public let isInProgress: Bool
    public let durationSeconds: Double?
    public let video: HDHomeRunRecordingVideoInfo?
    public let audio: [HDHomeRunRecordingAudioInfo]
    public let hasCaptions: Bool
    public let transcode: HDHomeRunTranscodeInfo

    enum CodingKeys: String, CodingKey {
        case isInProgress = "is_in_progress"
        case durationSeconds = "duration_seconds"
        case video
        case audio
        case hasCaptions = "has_captions"
        case transcode
    }
}

public struct HDHomeRunRecording: Identifiable, Codable, Sendable, Hashable {
    public var id: String {
        recordingId ?? playUrl ?? "\(title)_\(start ?? 0)"
    }

    public let recordingId: String?
    public let sessionId: String?
    public let playlistUrl: String?
    public let seriesId: String?
    public let title: String
    public let episodeTitle: String?
    public let seasonNumber: Int?
    public let episodeNumber: String?
    public let synopsis: String?
    public let channelNumber: String?
    public let channelName: String?
    public let start: TimeInterval?
    public let recordEnd: TimeInterval?
    public let playUrl: String?
    public let imageUrl: String?
    public let durationSeconds: Double?
    public let fileSizeBytes: Int64?
    public let hasCaptions: Bool?
    public let videoCodec: String?
    public let videoWidth: Int?
    public let videoHeight: Int?
    public let audioCodec: String?
    public let audioChannels: Int?
    public let originalAirDate: String?
    public let category: String?
    public let categoryType: String?
    public let isDvrFile: Bool?
    public let provider: String?

    enum CodingKeys: String, CodingKey {
        case recordingId = "recording_id"
        case sessionId = "session_id"
        case playlistUrl = "playlist_url"
        case seriesId = "series_id"
        case title
        case episodeTitle = "episode_title"
        case seasonNumber = "season_number"
        case episodeNumber = "episode_number"
        case synopsis
        case channelNumber = "channel_number"
        case channelName = "channel_name"
        case start
        case recordEnd = "record_end"
        case playUrl = "play_url"
        case imageUrl = "image_url"
        case durationSeconds = "duration_seconds"
        case fileSizeBytes = "file_size_bytes"
        case hasCaptions = "has_captions"
        case videoCodec = "video_codec"
        case videoWidth = "video_width"
        case videoHeight = "video_height"
        case audioCodec = "audio_codec"
        case audioChannels = "audio_channels"
        case originalAirDate = "original_air_date"
        case category
        case categoryType = "category_type"
        case isDvrFile = "is_dvr_file"
        case provider
    }

    public init(
        recordingId: String? = nil,
        sessionId: String? = nil,
        playlistUrl: String? = nil,
        seriesId: String? = nil,
        title: String,
        episodeTitle: String? = nil,
        seasonNumber: Int? = nil,
        episodeNumber: String? = nil,
        synopsis: String? = nil,
        channelNumber: String? = nil,
        channelName: String? = nil,
        start: TimeInterval? = nil,
        recordEnd: TimeInterval? = nil,
        playUrl: String? = nil,
        imageUrl: String? = nil,
        durationSeconds: Double? = nil,
        fileSizeBytes: Int64? = nil,
        hasCaptions: Bool? = nil,
        videoCodec: String? = nil,
        videoWidth: Int? = nil,
        videoHeight: Int? = nil,
        audioCodec: String? = nil,
        audioChannels: Int? = nil,
        originalAirDate: String? = nil,
        category: String? = nil,
        categoryType: String? = nil,
        isDvrFile: Bool? = nil,
        provider: String? = nil
    ) {
        self.recordingId = recordingId
        self.sessionId = sessionId
        self.playlistUrl = playlistUrl
        self.seriesId = seriesId
        self.title = title
        self.episodeTitle = episodeTitle
        self.seasonNumber = seasonNumber
        self.episodeNumber = episodeNumber
        self.synopsis = synopsis
        self.channelNumber = channelNumber
        self.channelName = channelName
        self.start = start
        self.recordEnd = recordEnd
        self.playUrl = playUrl
        self.imageUrl = imageUrl
        self.durationSeconds = durationSeconds
        self.fileSizeBytes = fileSizeBytes
        self.hasCaptions = hasCaptions
        self.videoCodec = videoCodec
        self.videoWidth = videoWidth
        self.videoHeight = videoHeight
        self.audioCodec = audioCodec
        self.audioChannels = audioChannels
        self.originalAirDate = originalAirDate
        self.category = category
        self.categoryType = categoryType
        self.isDvrFile = isDvrFile
        self.provider = provider
    }

    public var isInProgress: Bool {
        guard let end = recordEnd else { return false }
        return end > Date().timeIntervalSince1970
    }

    public var isHDHomeRunNative: Bool { provider == "hdhomerun" }

    public var formattedDuration: String {
        guard let dur = durationSeconds, dur > 0 else { return "" }
        let minutes = Int(dur / 60)
        let hours = minutes / 60
        let remMinutes = minutes % 60
        if hours > 0 {
            return "\(hours)h \(remMinutes)m"
        }
        return "\(minutes)m"
    }

    public var episodeDesignation: String? {
        if let s = seasonNumber, let e = episodeNumber {
            return "S\(s):E\(e)"
        }
        if let e = episodeNumber {
            return "Ep \(e)"
        }
        return nil
    }

    public var formattedFileSize: String {
        guard let bytes = fileSizeBytes, bytes > 0 else { return "" }
        let gb = Double(bytes) / 1_073_741_824.0
        if gb >= 1.0 {
            return String(format: "%.1f GB", gb)
        }
        let mb = Double(bytes) / 1_048_576.0
        return String(format: "%.0f MB", mb)
    }
}
