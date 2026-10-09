import HDHROpenKit
import SwiftUI

enum SettingsGroup: String, CaseIterable, Identifiable {
    case general
    case serverAndAdvanced

    var id: String {
        rawValue
    }

    var label: String {
        switch self {
        case .general: "General"
        case .serverAndAdvanced: "Server & Advanced"
        }
    }
}

public struct iOSSettingsView: View {
    @EnvironmentObject private var settingsViewModel: SettingsViewModel
    @EnvironmentObject private var serverDiscovery: ServerDiscovery
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var themeManager: ThemeManager
    @EnvironmentObject private var playbackPreferences: PlaybackPreferences

    @State private var selectedGroup: SettingsGroup = .general

    public init() {}

    public var body: some View {
        Form {
            Section {
                Picker("Settings group", selection: $selectedGroup) {
                    ForEach(SettingsGroup.allCases) { group in
                        Text(group.label).tag(group)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            }

            if selectedGroup == .general {
                // Appearance Section
                Section(header: Text("Appearance")) {
                    Picker("Theme", selection: $themeManager.mode) {
                        ForEach(ThemeMode.allCases, id: \.self) { mode in
                            Text(mode.label).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                }

                // Playback Section
                Section(header: Text("Playback")) {
                    Toggle("Auto-skip commercials", isOn: $playbackPreferences.autoSkipCommercialsEnabled)
                }

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
            }

            if selectedGroup == .serverAndAdvanced {
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
