import SwiftUI
import HDHROpenKit

public struct iOSServerConnectionFields: View {
    @EnvironmentObject private var environment: AppEnvironment
    @EnvironmentObject private var serverDiscovery: ServerDiscovery
    @EnvironmentObject private var settingsViewModel: SettingsViewModel

    @State private var serverURLInput: String = ""

    public init() {}

    public var body: some View {
        Group {
            TextField("Server URL", text: $serverURLInput)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .keyboardType(.URL)
                .onAppear { serverURLInput = serverDiscovery.serverURLString }
                .onSubmit { connect() }
                .task(id: serverURLInput) { await attemptAutoConnect(for: serverURLInput) }

            Button(action: connect) {
                Text("Connect")
            }
            .disabled(parsedURL(from: serverURLInput) == nil)

            Button(action: {
                if let url = serverDiscovery.currentServerURL {
                    Task { _ = await settingsViewModel.testServerConnection(url: url) }
                }
            }) {
                HStack {
                    Text("Test Connection")
                    Spacer()
                    if settingsViewModel.isTestingConnection {
                        ProgressView()
                    } else if let status = settingsViewModel.connectionStatus {
                        Text(status)
                            .font(.caption.bold())
                            .foregroundColor(status.contains("reachable") ? .green : .red)
                    }
                }
            }

            if !serverDiscovery.discoveredServers.isEmpty {
                ForEach(serverDiscovery.discoveredServers) { srv in
                    Button(action: {
                        serverURLInput = srv.url.absoluteString
                        Task { await environment.setServerURL(srv.url) }
                    }) {
                        HStack {
                            Text(srv.name)
                            Spacer()
                            Text(srv.url.absoluteString).font(.caption).foregroundColor(.secondary)
                        }
                    }
                }
            }
        }
    }

    private func parsedURL(from input: String) -> URL? {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        return URL(string: trimmed)
    }

    private func connect() {
        guard let url = parsedURL(from: serverURLInput) else { return }
        Task { await environment.setServerURL(url) }
    }

    // Debounced auto-connect: `.task(id:)` cancels and restarts this whenever
    // serverURLInput changes, so a pause in typing is what actually triggers
    // it - no manual Task/Timer bookkeeping needed.
    //
    // Unlike the manual button, this can fire on a still-incomplete address
    // (a pause mid-typing), so it must confirm reachability before
    // committing via serverDiscovery.testConnection - otherwise a failed
    // premature attempt would mark the bad value as "current"
    // (serverDiscovery.serverURLString), and since this function only
    // re-runs when serverURLInput itself changes, it would never retry on
    // its own even once the address is completed. The Connect button stays
    // enabled regardless of this state (see its `.disabled` above) so a
    // stuck/unreachable connection can always be retried by hand too.
    private func attemptAutoConnect(for input: String) async {
        try? await Task.sleep(nanoseconds: 800_000_000)
        guard !Task.isCancelled, input == serverURLInput else { return }
        guard let url = parsedURL(from: input) else { return }
        guard input != serverDiscovery.serverURLString else { return }
        guard await settingsViewModel.testServerConnection(url: url) else { return }
        await environment.setServerURL(url)
    }
}
