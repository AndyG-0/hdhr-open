import Foundation

public enum RecordingCategoryFilter: String, CaseIterable, Identifiable, Sendable {
    case all = "All"
    case shows = "Shows"
    case movies = "Movies"
    case sports = "Sports"
    case inProgress = "In Progress"

    public var id: String { rawValue }
}

@MainActor
public final class RecordingsViewModel: ObservableObject {
    @Published public private(set) var recordings: [HDHomeRunRecording] = []
    @Published public private(set) var recordingRules: [HDHomeRunRecordingRule] = []
    @Published public private(set) var dvrInfo: HDHomeRunDvrInfo?
    @Published public var selectedFilter: RecordingCategoryFilter = .all
    @Published public private(set) var isLoading: Bool = false
    @Published public private(set) var error: String?

    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public var filteredRecordings: [HDHomeRunRecording] {
        switch selectedFilter {
        case .all:
            return recordings
        case .shows:
            return recordings.filter { $0.categoryType == "shows" || ($0.categoryType == nil && $0.seasonNumber != nil) }
        case .movies:
            return recordings.filter { $0.categoryType == "movies" || $0.category?.lowercased().contains("movie") == true }
        case .sports:
            return recordings.filter { $0.categoryType == "sports" || $0.category?.lowercased().contains("sport") == true }
        case .inProgress:
            return recordings.filter { $0.isInProgress }
        }
    }

    public var inProgressRecordings: [HDHomeRunRecording] {
        recordings.filter { $0.isInProgress }
    }

    public var completedRecordings: [HDHomeRunRecording] {
        recordings.filter { !$0.isInProgress }
    }

    public func loadData() async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        async let recsTask = loadRecordings()
        async let rulesTask = loadRules()
        async let infoTask = loadDvrInfo()

        _ = await (recsTask, rulesTask, infoTask)
    }

    public func loadRecordings() async {
        do {
            self.recordings = try await apiClient.listRecordings()
        } catch {
            self.error = error.localizedDescription
            Log.dvr.error("Failed to load recordings: \(error.localizedDescription)")
        }
    }

    public func loadRules() async {
        do {
            self.recordingRules = try await apiClient.listRecordingRules()
        } catch {
            Log.dvr.warning("Failed to load rules: \(error.localizedDescription)")
        }
    }

    public func loadDvrInfo() async {
        do {
            self.dvrInfo = try await apiClient.getDvrInfo()
        } catch {
            Log.dvr.debug("Failed to load DVR info: \(error.localizedDescription)")
        }
    }

    public func deleteRecording(_ recording: HDHomeRunRecording) async throws {
        guard let id = recording.recordingId else { return }
        try await apiClient.deleteRecording(id: id)
        self.recordings.removeAll { $0.recordingId == id }
    }

    public func deleteRule(ruleId: String) async throws {
        self.recordingRules = try await apiClient.deleteRecordingRule(id: ruleId)
    }
}
