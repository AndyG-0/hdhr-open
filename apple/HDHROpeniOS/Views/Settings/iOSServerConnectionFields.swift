import HDHROpenKit
import SwiftUI

public struct iOSServerConnectionFields: View {
    @EnvironmentObject private var environment: AppEnvironment
    @EnvironmentObject private var serverDiscovery: ServerDiscovery
    @EnvironmentObject private var settingsViewModel: SettingsViewModel

    @State private var serverURLInput = ""

    public init() {}

    public var body: some View {
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
        .disabled(settingsViewModel.parsedServerURL(from: serverURLInput) == nil)

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

    private func connect() {
        guard let url = settingsViewModel.parsedServerURL(from: serverURLInput) else { return }
        Task { await environment.setServerURL(url) }
    }

    /// Debounced auto-connect: `.task(id:)` cancels and restarts this whenever
    /// serverURLInput changes, so a pause in typing is what actually triggers
    /// it - no manual Task/Timer bookkeeping needed. The actual debounce,
    /// parsing/validation, and reachability check live in
    /// `SettingsViewModel.attemptAutoConnect`, shared with tvOS; this just
    /// re-checks that nothing changed out from under it before committing.
    /// The Connect button stays enabled regardless of this state (see its
    /// `.disabled` above) so a stuck/unreachable connection can always be
    /// retried by hand too.
    private func attemptAutoConnect(for input: String) async {
        guard let url = await settingsViewModel.attemptAutoConnect(
            for: input,
            currentServerURLString: serverDiscovery.serverURLString
        ) else { return }
        guard input == serverURLInput else { return }
        await environment.setServerURL(url)
    }
}
