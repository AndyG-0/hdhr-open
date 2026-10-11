import Foundation

public enum DiscoveryBucketFilter: String, CaseIterable, Sendable {
    case all
    case shows
    case movies
    case sports

    public var bucket: String? {
        self == .all ? nil : rawValue
    }

    public var label: String {
        switch self {
        case .all: "All"
        case .shows: "Shows"
        case .movies: "Movies"
        case .sports: "Sports"
        }
    }
}

@MainActor
public final class DiscoveryViewModel: ObservableObject {
    @Published public private(set) var items: [HDHomeRunGuideEntry] = []
    @Published public private(set) var hasProfile = false
    @Published public private(set) var enabled = false
    @Published public private(set) var isLoading = false
    @Published public private(set) var error: String?
    @Published public var filter: DiscoveryBucketFilter = .all

    /// Local filter over the single fetch above - selecting a bucket never
    /// triggers a second network call.
    public var filteredItems: [HDHomeRunGuideEntry] {
        guard let bucket = filter.bucket else { return items }
        return items.filter { $0.bucket == bucket }
    }

    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func loadData() async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            let response = try await apiClient.getDiscovery()
            enabled = response.enabled
            hasProfile = response.hasProfile
            items = response.items
        } catch {
            self.error = error.localizedDescription
            Log.dvr.error("Failed to load discovery: \(error.localizedDescription)")
        }
    }
}
