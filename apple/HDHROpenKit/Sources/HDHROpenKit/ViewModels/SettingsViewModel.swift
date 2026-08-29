import Foundation

@MainActor
public final class SettingsViewModel: ObservableObject {
    @Published public private(set) var appSettings: AppSettings?
    @Published public private(set) var transcodePresets: [HDHomeRunTranscodePreset] = []
    @Published public private(set) var hwaccelDiagnostics: HWAccelDiagnostics?
    @Published public private(set) var networkIntegrations: [NetworkIntegration] = []
    @Published public private(set) var registeredDevices: [DeviceListEntry] = []
    @Published public private(set) var currentDevice: DeviceInfo?
    @Published public private(set) var currentPresetId: String = "software"
    @Published public private(set) var isSavingPreset: Bool = false
    @Published public private(set) var isLoading: Bool = false
    @Published public private(set) var isTestingConnection: Bool = false
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
            self.appSettings = try await apiClient.getSettings()
        } catch {
            Log.general.warning("Failed to load settings: \(error.localizedDescription)")
        }
    }

    public func loadPresets() async {
        do {
            self.transcodePresets = try await apiClient.getTranscodePresets()
        } catch {
            Log.general.debug("Failed to load transcode presets: \(error.localizedDescription)")
        }
    }

    public func loadIntegrations() async {
        do {
            self.networkIntegrations = try await apiClient.listNetworkIntegrations()
            self.currentPresetId = Self.presetId(from: networkIntegrations)
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
              let hwaccel = hdhomerun.settings["hwaccel"]?.value as? String else {
            return "software"
        }
        return hwaccel
    }

    public func loadDevices() async {
        do {
            self.registeredDevices = try await apiClient.listDevices()
            self.currentDevice = try await apiClient.getCurrentDevice()
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
}
