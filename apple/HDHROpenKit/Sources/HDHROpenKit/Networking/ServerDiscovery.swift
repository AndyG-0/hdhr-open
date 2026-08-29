import Foundation
import Network

public struct DiscoveredServer: Identifiable, Hashable, Sendable {
    public var id: String { url.absoluteString }
    public let name: String
    public let url: URL
    public let isReachable: Bool

    public init(name: String, url: URL, isReachable: Bool = true) {
        self.name = name
        self.url = url
        self.isReachable = isReachable
    }
}

@MainActor
public final class ServerDiscovery: ObservableObject {
    @Published public private(set) var discoveredServers: [DiscoveredServer] = []
    @Published public private(set) var isSearching: Bool = false
    @Published public var serverURLString: String {
        didSet {
            UserDefaults.standard.set(serverURLString, forKey: serverURLStorageKey)
        }
    }

    private let serverURLStorageKey = "org.hdhropen.client.serverURL"
    private var browser: NWBrowser?

    public init(defaultURL: String = "http://127.0.0.1:8000") {
        let stored = UserDefaults.standard.string(forKey: "org.hdhropen.client.serverURL")
        self.serverURLString = stored ?? defaultURL
    }

    public var currentServerURL: URL? {
        URL(string: serverURLString)
    }

    public func startDiscovery() {
        guard !isSearching else { return }
        isSearching = true
        discoveredServers.removeAll()

        let descriptor = NWBrowser.Descriptor.bonjour(type: "_http._tcp", domain: "local.")
        let parameters = NWParameters()
        let browser = NWBrowser(for: descriptor, using: parameters)

        browser.stateUpdateHandler = { [weak self] state in
            guard let self = self else { return }
            switch state {
            case .ready:
                Log.network.info("Bonjour browser ready")
            case .failed(let error):
                Log.network.error("Bonjour browser failed: \(error.localizedDescription)")
                Task { @MainActor in self.isSearching = false }
            default:
                break
            }
        }

        browser.browseResultsChangedHandler = { [weak self] results, _ in
            guard let self = self else { return }
            for result in results {
                if case .service(let name, _, _, _) = result.endpoint {
                    if name.lowercased().contains("hdhr") || name.lowercased().contains("homerun") {
                        Task { @MainActor in
                            if let url = URL(string: "http://\(name).local:8000") {
                                let server = DiscoveredServer(name: name, url: url)
                                if !self.discoveredServers.contains(where: { $0.id == server.id }) {
                                    self.discoveredServers.append(server)
                                }
                            }
                        }
                    }
                }
            }
        }

        browser.start(queue: .main)
        self.browser = browser
    }

    public func stopDiscovery() {
        browser?.cancel()
        browser = nil
        isSearching = false
    }

    public func testConnection(to url: URL) async -> Bool {
        guard let checkURL = URL(string: "/api/setup/status", relativeTo: url) else { return false }
        var request = URLRequest(url: checkURL)
        request.timeoutInterval = 3.0
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) {
                return true
            }
        } catch {
            return false
        }
        return false
    }
}
