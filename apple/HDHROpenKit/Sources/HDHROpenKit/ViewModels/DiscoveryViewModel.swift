import Foundation

@MainActor
public final class DiscoveryViewModel: ObservableObject {
    @Published public private(set) var items: [HDHomeRunGuideEntry] = []
    @Published public private(set) var hasProfile = false
    @Published public private(set) var enabled = false
    @Published public private(set) var isLoading = false
    @Published public private(set) var error: String?

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
