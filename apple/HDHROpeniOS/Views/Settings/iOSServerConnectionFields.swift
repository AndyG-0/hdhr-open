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
                .onSubmit {
                    if let url = URL(string: serverURLInput) {
                        Task { await environment.setServerURL(url) }
                    }
                }

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
}
