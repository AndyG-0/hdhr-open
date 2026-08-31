import SwiftUI
import HDHROpenKit

public struct TVSettingsView: View {
    @EnvironmentObject private var settingsViewModel: SettingsViewModel
    @EnvironmentObject private var serverDiscovery: ServerDiscovery
    @EnvironmentObject private var authManager: AuthManager
    @EnvironmentObject private var themeManager: ThemeManager

    @FocusState private var focusedPresetId: String?
    @FocusState private var focusedThemeMode: ThemeMode?

    public init() {}

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 28) {
                // Header
                Text("Settings")
                    .font(.largeTitle.bold())
                    .foregroundColor(Theme.textPrimary)
                    .padding(.horizontal, 48)
                    .padding(.top, 24)

                ScrollView {
                    VStack(alignment: .leading, spacing: 36) {
                        // Appearance Section
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Appearance")
                                .font(.title3.bold())
                                .foregroundColor(.secondary)

                            HStack(spacing: 16) {
                                Spacer()

                                ForEach(ThemeMode.allCases, id: \.self) { mode in
                                    let isActive = themeManager.mode == mode
                                    let isFocused = focusedThemeMode == mode

                                    Button(action: { themeManager.mode = mode }) {
                                        Text(mode.label)
                                            .font(.headline)
                                            .foregroundColor(isActive ? .white : Theme.textPrimary)
                                            .padding(.horizontal, 24)
                                            .padding(.vertical, 12)
                                            .background(isActive ? Color.blue : Theme.appSurfaceVariant)
                                            .cornerRadius(12)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 12)
                                                    .stroke(isFocused ? Theme.textPrimary : Color.clear, lineWidth: 4)
                                            )
                                            .scaleEffect(isFocused ? 1.05 : 1.0)
                                            .animation(.easeInOut(duration: 0.15), value: isFocused)
                                    }
                                    .buttonStyle(.plain)
                                    .focused($focusedThemeMode, equals: mode)
                                }
                            }
                            .padding(24)
                            .background(Theme.appSurface)
                            .cornerRadius(16)
                        }
                        .focusSection()

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
                                            .foregroundColor(Theme.textPrimary)
                                        Text("Role: \(user.role.rawValue.capitalized)")
                                            .font(.subheadline)
                                            .foregroundColor(Theme.textSecondary)
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
                            .background(Theme.appSurface)
                            .cornerRadius(16)
                        }
                        .focusSection()

                        // Server Connection Section
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Server Connection")
                                .font(.title3.bold())
                                .foregroundColor(.secondary)

                            TVServerConnectionFields()
                                .padding(24)
                                .background(Theme.appSurface)
                                .cornerRadius(16)
                        }
                        .focusSection()

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
                                            .background(isActive ? Theme.accentSubtle : Theme.appSurface)
                                            .cornerRadius(12)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 12)
                                                    .stroke(isFocused ? Theme.textPrimary : Color.clear, lineWidth: 4)
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
                            .focusSection()
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
