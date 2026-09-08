import HDHROpenKit
import SwiftUI

public struct TVServerConnectionFields: View {
    @EnvironmentObject private var environment: AppEnvironment
    @EnvironmentObject private var serverDiscovery: ServerDiscovery
    @EnvironmentObject private var settingsViewModel: SettingsViewModel

    @State private var serverURLInput = ""
    @State private var isEditingServer = false

    public init() {}

    public var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Backend Server URL")
                        .font(.headline)
                        .foregroundColor(Theme.textPrimary)

                    if isEditingServer {
                        TextField("http://192.168.1.10:8000", text: $serverURLInput)
                            .font(.subheadline.monospaced())
                    } else {
                        Text(serverDiscovery.serverURLString)
                            .font(.subheadline.monospaced())
                            .foregroundColor(.blue)
                    }
                }

                Spacer()

                HStack {
                    if isEditingServer {
                        Button(role: .cancel, action: {
                            isEditingServer = false
                        }) {
                            Text("Cancel")
                        }

                        Button(action: {
                            if let url = URL(string: serverURLInput) {
                                Task { await environment.setServerURL(url) }
                            }
                            isEditingServer = false
                        }) {
                            Text("Save")
                        }
                    } else {
                        Button(action: {
                            serverURLInput = serverDiscovery.serverURLString
                            isEditingServer = true
                        }) {
                            Label("Edit", systemImage: "pencil")
                        }

                        Button(action: {
                            if let url = serverDiscovery.currentServerURL {
                                Task { _ = await settingsViewModel.testServerConnection(url: url) }
                            }
                        }) {
                            if settingsViewModel.isTestingConnection {
                                ProgressView()
                            } else {
                                Label("Test Connection", systemImage: "bolt.horizontal.fill")
                            }
                        }
                    }
                }
                .focusSection()
            }

            if let status = settingsViewModel.connectionStatus {
                Text(status)
                    .font(.caption.bold())
                    .foregroundColor(status.contains("reachable") ? .green : .red)
            }

            if !serverDiscovery.discoveredServers.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Discovered on Local Network (LAN):")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    ForEach(serverDiscovery.discoveredServers) { srv in
                        Button(action: {
                            Task { await environment.setServerURL(srv.url) }
                        }) {
                            HStack {
                                Label(srv.name, systemImage: "server.rack")
                                Spacer()
                                Text(srv.url.absoluteString)
                                    .font(.caption.monospaced())
                            }
                        }
                    }
                }
                .focusSection()
                .padding(.top, 8)
            }
        }
    }
}
