import Foundation

@MainActor
public final class TunerViewModel: ObservableObject {
    @Published public private(set) var tuners: [HDHomeRunTuner] = []
    @Published public private(set) var tunerInfo: HDHomeRunTunerInfo?
    @Published public private(set) var isLoading = false
    @Published public private(set) var isPolling = false

    private let apiClient: APIClient
    private var pollTask: Task<Void, Never>?

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func loadData() async {
        isLoading = true
        defer { isLoading = false }

        async let statusTask = loadStatus()
        async let infoTask = loadInfo()
        _ = await (statusTask, infoTask)
    }

    public func loadStatus() async {
        do {
            tuners = try await apiClient.getTunerStatus()
        } catch {
            Log.general.warning("Failed to load tuner status: \(error.localizedDescription)")
        }
    }

    public func loadInfo() async {
        do {
            tunerInfo = try await apiClient.getTunerInfo()
        } catch {
            Log.general.warning("Failed to load tuner info: \(error.localizedDescription)")
        }
    }

    public func startPolling(intervalSeconds: UInt64 = 2) {
        guard pollTask == nil else { return }
        isPolling = true
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { break }
                await loadStatus()
                try? await Task.sleep(nanoseconds: intervalSeconds * 1_000_000_000)
            }
        }
    }

    public func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
        isPolling = false
    }
}
