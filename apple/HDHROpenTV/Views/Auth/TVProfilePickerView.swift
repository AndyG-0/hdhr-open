import SwiftUI
import HDHROpenKit

public struct TVProfilePickerView: View {
    @EnvironmentObject private var authViewModel: AuthViewModel
    @EnvironmentObject private var authManager: AuthManager

    @State private var showServerSetup: Bool = false

    public init() {}

    public var body: some View {
        VStack(spacing: 36) {
            Spacer()

            VStack(spacing: 8) {
                Text("Who's Watching?")
                    .font(.system(size: 48, weight: .bold))
                    .foregroundColor(Theme.textPrimary)

                Text("Select your profile to load preferences and guide settings")
                    .font(.title3)
                    .foregroundColor(.secondary)

                HStack(spacing: 24) {
                    Button(action: { Task { await authManager.fetchProfiles() } }) {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                    .disabled(authManager.isLoading)

                    Button(action: { showServerSetup = true }) {
                        Label("Server Settings", systemImage: "gearshape")
                    }
                }
                .padding(.top, 8)
            }

            if authManager.isLoading && authViewModel.profiles.isEmpty {
                ProgressView()
                    .scaleEffect(2.0)
            } else {
                HStack(spacing: 36) {
                    ForEach(authViewModel.profiles) { profile in
                        ProfileAvatarButton(profile: profile) {
                            authViewModel.selectProfile(profile)
                        }
                    }
                }
                .padding(.horizontal, 48)
            }

            if let err = authViewModel.errorMessage ?? authManager.authError {
                Text(err)
                    .font(.headline)
                    .foregroundColor(.red)
            }

            Spacer()
        }
        .task {
            if authViewModel.profiles.isEmpty {
                await authManager.fetchProfiles()
            }
        }
        .sheet(isPresented: $showServerSetup) {
            TVServerSetupView()
        }
    }
}

struct ProfileAvatarButton: View {
    let profile: UserProfile
    let onSelect: () -> Void

    @FocusState private var isFocused: Bool

    var body: some View {
        Button(action: onSelect) {
            VStack(spacing: 12) {
                ZStack {
                    Circle()
                        .fill(Theme.appSurfaceVariant)
                        .frame(width: 140, height: 140)

                    if let avatar = profile.avatar, let url = URL(string: avatar) {
                        AsyncImage(url: url) { image in
                            image.resizable().aspectRatio(contentMode: .fill)
                        } placeholder: {
                            Text(String(profile.name.prefix(1)).uppercased())
                                .font(.system(size: 52, weight: .bold))
                                .foregroundColor(Theme.textPrimary)
                        }
                        .frame(width: 140, height: 140)
                        .clipShape(Circle())
                    } else {
                        Text(String(profile.name.prefix(1)).uppercased())
                            .font(.system(size: 52, weight: .bold))
                            .foregroundColor(Theme.textPrimary)
                    }

                    if profile.hasPin {
                        VStack {
                            Spacer()
                            HStack {
                                Spacer()
                                Image(systemName: "lock.fill")
                                    .font(.caption)
                                    .padding(6)
                                    .background(Color.black.opacity(0.8))
                                    .clipShape(Circle())
                                    .foregroundColor(.yellow)
                            }
                        }
                        .frame(width: 140, height: 140)
                    }
                }
                .overlay(
                    Circle()
                        .stroke(isFocused ? Theme.textPrimary : Color.clear, lineWidth: 5)
                )

                Text(profile.name)
                    .font(.headline)
                    .foregroundColor(isFocused ? Theme.textPrimary : .secondary)
            }
            .scaleEffect(isFocused ? 1.1 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: isFocused)
        }
        .buttonStyle(.plain)
        .focused($isFocused)
    }
}
