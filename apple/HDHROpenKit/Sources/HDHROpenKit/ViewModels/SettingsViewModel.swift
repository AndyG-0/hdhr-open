import Foundation

@MainActor
public final class SettingsViewModel: ObservableObject {
    @Published public private(set) var appSettings: AppSettings?
    @Published public private(set) var transcodePresets: [HDHomeRunTranscodePreset] = []
    @Published public private(set) var hwaccelDiagnostics: HWAccelDiagnostics?
    @Published public private(set) var networkIntegrations: [NetworkIntegration] = []
    @Published public private(set) var registeredDevices: [DeviceListEntry] = []
    @Published public private(set) var currentDevice: DeviceInfo?
    @Published public private(set) var currentPresetId = "software"
    @Published public private(set) var isSavingPreset = false
    @Published public private(set) var isLoading = false
    @Published public private(set) var isTestingConnection = false
    @Published public private(set) var connectionStatus: String?

    private let apiClient: APIClient
    private let serverDiscovery: ServerDiscovery

    public init(apiClient: APIClient, serverDiscovery: ServerDiscovery) {
        self.apiClient = apiClient
        self.serverDiscovery = serverDiscovery
    }

    public func loadData() async {
        isLoading = true
        defer { isLoading = false }

        async let settingsTask = loadAppSettings()
        async let presetsTask = loadPresets()
        async let integrationsTask = loadIntegrations()
        async let devicesTask = loadDevices()

        _ = await (settingsTask, presetsTask, integrationsTask, devicesTask)
    }

    public func loadAppSettings() async {
        do {
            appSettings = try await apiClient.getSettings()
        } catch {
            Log.general.warning("Failed to load settings: \(error.localizedDescription)")
        }
    }

    public func loadPresets() async {
        do {
            transcodePresets = try await apiClient.getTranscodePresets()
        } catch {
            Log.general.debug("Failed to load transcode presets: \(error.localizedDescription)")
        }
    }

    public func loadIntegrations() async {
        do {
            networkIntegrations = try await apiClient.listNetworkIntegrations()
            currentPresetId = Self.presetId(from: networkIntegrations)
        } catch {
            Log.general.debug("Failed to load network integrations: \(error.localizedDescription)")
        }
    }

    public func selectPreset(_ id: String) async {
        guard id != currentPresetId else { return }

        let previousPresetId = currentPresetId
        isSavingPreset = true
        defer { isSavingPreset = false }

        currentPresetId = id
        do {
            let updated = try await apiClient.updateNetworkIntegration(type: "hdhomerun", settings: ["hwaccel": AnyCodable(id)])
            if let index = networkIntegrations.firstIndex(where: { $0.type == "hdhomerun" }) {
                networkIntegrations[index] = updated
            }
        } catch {
            Log.general.warning("Failed to update transcode preset: \(error.localizedDescription)")
            currentPresetId = previousPresetId
        }
    }

    private static func presetId(from integrations: [NetworkIntegration]) -> String {
        guard let hdhomerun = integrations.first(where: { $0.type == "hdhomerun" }),
              let hwaccel = hdhomerun.settings["hwaccel"]?.value as? String
        else {
            return "software"
        }
        return hwaccel
    }

    public func loadDevices() async {
        do {
            registeredDevices = try await apiClient.listDevices()
            currentDevice = try await apiClient.getCurrentDevice()
        } catch {
            Log.general.debug("Failed to load devices: \(error.localizedDescription)")
        }
    }

    public func testServerConnection(url: URL) async -> Bool {
        isTestingConnection = true
        defer { isTestingConnection = false }
        let ok = await serverDiscovery.testConnection(to: url)
        connectionStatus = ok ? "Server reachable" : "Server unreachable"
        return ok
    }

    // MARK: - Server URL Validation

    /// Parses a server-URL text field's contents into a `URL`, requiring both
    /// a scheme and a host so inputs like "192.168.1.10" (no scheme) or
    /// "http://" (no host) are rejected - `URL(string:)` alone would accept
    /// those and leave callers thinking they have a connectable address.
    /// Shared by iOS and tvOS so "Connect"/"Save" is enabled under identical
    /// conditions on both platforms.
    public func parsedServerURL(from input: String) -> URL? {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), url.scheme != nil, url.host != nil else {
            return nil
        }
        return url
    }

    /// Debounced auto-connect shared by both platforms' server-URL text
    /// fields: callers re-invoke this from a `.task(id:)` keyed on the raw
    /// input, so a still-in-progress call is cancelled automatically as soon
    /// as the text changes again - only a pause in typing lets it run to
    /// completion.
    ///
    /// This can be reached with a still-incomplete address (a pause
    /// mid-typing), so it must confirm reachability before returning a URL -
    /// otherwise a failed premature attempt would get committed as "current"
    /// and, since this only re-runs when the input itself changes, it would
    /// never retry on its own once the address is completed. Returns `nil`
    /// when there's nothing to do; the caller is responsible for actually
    /// committing the URL (e.g. via `AppEnvironment.setServerURL`).
    public func attemptAutoConnect(for input: String, currentServerURLString: String) async -> URL? {
        try? await Task.sleep(nanoseconds: 800_000_000)
        guard !Task.isCancelled else { return nil }
        guard let url = parsedServerURL(from: input) else { return nil }
        guard input != currentServerURLString else { return nil }
        guard await testServerConnection(url: url) else { return nil }
        return url
    }
}
