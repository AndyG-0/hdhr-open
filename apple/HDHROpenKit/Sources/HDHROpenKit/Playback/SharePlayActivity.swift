import Foundation
import GroupActivities

/// The shared "what are we watching" activity broadcast over FaceTime for
/// native SharePlay (SHARE-1). Mirrors `SyncPlayContent`'s selector-only
/// shape - only `channelNumber`/`recordingId`/`title` cross the wire, never
/// a stream URL, since each participant negotiates its own HLS session
/// against its own server (see `PlayerViewModel.handleRemoteContentChange`).
public struct WatchProgramActivity: GroupActivity, Sendable {
    public static let activityIdentifier = "org.hdhropen.watch-program"

    public let channelNumber: String?
    public let recordingId: String?
    public let title: String

    public init(channelNumber: String? = nil, recordingId: String? = nil, title: String) {
        self.channelNumber = channelNumber
        self.recordingId = recordingId
        self.title = title
    }

    public init(content: SyncPlayContent) {
        self.channelNumber = content.channelNumber
        self.recordingId = content.recordingId
        self.title = content.title
    }

    public var metadata: GroupActivityMetadata {
        get async {
            var metadata = GroupActivityMetadata()
            metadata.title = title
            metadata.type = .watchTogether
            metadata.supportsContinuationOnTV = true
            return metadata
        }
    }
}
