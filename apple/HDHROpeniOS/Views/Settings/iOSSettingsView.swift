import SwiftUI
import HDHROpenKit

public struct iOSSettingsView: View {
    @EnvironmentObject private var settingsViewModel: SettingsViewModel
    @EnvironmentObject private var serverDiscovery: ServerDiscovery
    @EnvironmentObject private var authManager: AuthManager

    public init() {}

    public var body: some View {
        Form {
            // Profile Section
            Section(header: Text("Profile")) {
                if let user = authManager.currentUser {
                    HStack {
                        VStack(alignment: .leading) {
                            Text(user.name).font(.headline)
                            Text("Role: \(user.role.rawValue.capitalized)").font(.caption).foregroundColor(.secondary)
                        }
                        Spacer()
                        Button("Logout") {
                            Task { await authManager.logout() }
                        }
                        .foregroundColor(.red)
                    }
                }
            }

            // Server Connection
            Section(header: Text("Server Connection")) {
                iOSServerConnectionFields()
            }

            // Transcode Presets
            if !settingsViewModel.transcodePresets.isEmpty {
                Section(header: Text("Transcode Presets")) {
                    ForEach(settingsViewModel.transcodePresets) { preset in
                        Button(action: {
                            Task { await settingsViewModel.selectPreset(preset.id) }
                        }) {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    HStack {
                                        Text(preset.label).font(.subheadline.bold())
                                        if preset.hardware {
                                            Text("HW").font(.caption2.bold()).padding(.horizontal, 4).background(Color.green.opacity(0.2)).cornerRadius(3)
                                        }
                                    }
                                    Text(preset.description).font(.caption).foregroundColor(.secondary)
                                }
                                Spacer()
                                if preset.id == settingsViewModel.currentPresetId {
                                    Image(systemName: "checkmark")
                                        .foregroundColor(.accentColor)
                                }
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(settingsViewModel.isSavingPreset)
                    }
                }
            }
        }
        .navigationTitle("Settings")
        .task {
            await settingsViewModel.loadData()
            serverDiscovery.startDiscovery()
        }
        .onDisappear {
            serverDiscovery.stopDiscovery()
        }
    }
}
