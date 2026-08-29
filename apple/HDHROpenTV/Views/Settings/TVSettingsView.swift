import SwiftUI
import HDHROpenKit

public struct TVSettingsView: View {
    @EnvironmentObject private var settingsViewModel: SettingsViewModel
    @EnvironmentObject private var serverDiscovery: ServerDiscovery
    @EnvironmentObject private var authManager: AuthManager

    @FocusState private var focusedPresetId: String?

    public init() {}

    public var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 28) {
                // Header
                Text("Settings")
                    .font(.largeTitle.bold())
                    .foregroundColor(.white)
                    .padding(.horizontal, 48)
                    .padding(.top, 24)

                ScrollView {
                    VStack(alignment: .leading, spacing: 36) {
                        // Profile Section
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Current Profile")
                                .font(.title3.bold())
                                .foregroundColor(.secondary)

                            HStack(spacing: 20) {
                                if let user = authManager.currentUser {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(user.name)
                                            .font(.title2.bold())
                                            .foregroundColor(.white)
                                        Text("Role: \(user.role.rawValue.capitalized)")
                                            .font(.subheadline)
                                            .foregroundColor(.gray)
                                    }

                                    Spacer()

                                    Button(role: .destructive, action: {
                                        Task { await authManager.logout() }
                                    }) {
                                        Label("Switch Profile / Logout", systemImage: "person.crop.circle.badge.xmark")
                                    }
                                }
                            }
                            .padding(24)
                            .background(Color(white: 0.12))
                            .cornerRadius(16)
                        }

                        // Server Connection Section
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Server Connection")
                                .font(.title3.bold())
                                .foregroundColor(.secondary)

                            TVServerConnectionFields()
                                .padding(24)
                                .background(Color(white: 0.12))
                                .cornerRadius(16)
                        }

                        // Hardware Acceleration Info
                        if !settingsViewModel.transcodePresets.isEmpty {
                            VStack(alignment: .leading, spacing: 16) {
                                Text("Transcoder Presets")
                                    .font(.title3.bold())
                                    .foregroundColor(.secondary)

                                LazyVStack(spacing: 12) {
                                    ForEach(settingsViewModel.transcodePresets) { preset in
                                        let isActive = preset.id == settingsViewModel.currentPresetId
                                        let isFocused = focusedPresetId == preset.id

                                        Button(action: {
                                            Task { await settingsViewModel.selectPreset(preset.id) }
                                        }) {
                                            HStack {
                                                VStack(alignment: .leading, spacing: 2) {
                                                    HStack {
                                                        Text(preset.label)
                                                            .font(.headline)
                                                        if preset.hardware {
                                                            Text("HW")
                                                                .font(.caption.bold())
                                                                .padding(.horizontal, 4)
                                                                .background(Color.green.opacity(0.6))
                                                                .cornerRadius(3)
                                                        }
                                                    }
                                                    Text(preset.description)
                                                        .font(.caption)
                                                        .foregroundColor(.secondary)
                                                }
                                                Spacer()
                                                if isActive {
                                                    Image(systemName: "checkmark.circle.fill")
                                                        .foregroundColor(.blue)
                                                }
                                            }
                                            .padding(16)
                                            .background(isActive ? Color.blue.opacity(0.15) : Color(white: 0.12))
                                            .cornerRadius(12)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 12)
                                                    .stroke(isFocused ? Color.white : Color.clear, lineWidth: 4)
                                            )
                                            .scaleEffect(isFocused ? 1.05 : 1.0)
                                            .animation(.easeInOut(duration: 0.15), value: isFocused)
                                        }
                                        .buttonStyle(.plain)
                                        .focused($focusedPresetId, equals: preset.id)
                                        .disabled(settingsViewModel.isSavingPreset)
                                    }
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 48)
                    .padding(.bottom, 64)
                }
            }
        }
        .task {
            await settingsViewModel.loadData()
            serverDiscovery.startDiscovery()
        }
        .onDisappear {
            serverDiscovery.stopDiscovery()
        }
    }
}
