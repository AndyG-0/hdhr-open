import SwiftUI
import HDHROpenKit

public struct iOSProfilePickerView: View {
    @EnvironmentObject private var authViewModel: AuthViewModel
    @EnvironmentObject private var authManager: AuthManager

    @State private var pinDialogProfile: UserProfile?
    @State private var pinText: String = ""
    @State private var showServerSetup: Bool = false

    public init() {}

    private let columns = [
        GridItem(.adaptive(minimum: 120, maximum: 160), spacing: 20)
    ]

    public var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                Spacer()

                Text("Who's Watching?")
                    .font(.largeTitle.bold())

                if authManager.isLoading && authViewModel.profiles.isEmpty {
                    ProgressView()
                } else {
                    LazyVGrid(columns: columns, spacing: 24) {
                        ForEach(authViewModel.profiles) { profile in
                            Button(action: {
                                if profile.hasPin {
                                    pinDialogProfile = profile
                                    pinText = ""
                                } else {
                                    authViewModel.selectProfile(profile)
                                }
                            }) {
                                VStack(spacing: 8) {
                                    ZStack(alignment: .bottomTrailing) {
                                        Circle()
                                            .fill(Color.blue.opacity(0.2))
                                            .frame(width: 90, height: 90)

                                        if let avatar = profile.avatar, let url = URL(string: avatar) {
                                            AsyncImage(url: url) { image in
                                                image.resizable().aspectRatio(contentMode: .fill)
                                            } placeholder: {
                                                Text(String(profile.name.prefix(1)).uppercased())
                                                    .font(.title.bold())
                                                    .foregroundColor(.blue)
                                            }
                                            .frame(width: 90, height: 90)
                                            .clipShape(Circle())
                                        } else {
                                            Text(String(profile.name.prefix(1)).uppercased())
                                                .font(.title.bold())
                                                .foregroundColor(.blue)
                                        }

                                        if profile.hasPin {
                                            Image(systemName: "lock.fill")
                                                .font(.caption)
                                                .padding(5)
                                                .background(Color.yellow)
                                                .clipShape(Circle())
                                                .foregroundColor(.black)
                                        }
                                    }

                                    Text(profile.name)
                                        .font(.headline)
                                        .foregroundColor(.primary)
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 32)
                }

                if let err = authViewModel.errorMessage ?? authManager.authError {
                    Text(err)
                        .font(.subheadline)
                        .foregroundColor(.red)
                }

                Spacer()
            }
            .navigationTitle("Profiles")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: { Task { await authManager.fetchProfiles() } }) {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(authManager.isLoading)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: { showServerSetup = true }) {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showServerSetup) {
                iOSServerSetupView()
            }
            .alert("Enter PIN", isPresented: Binding(
                get: { pinDialogProfile != nil },
                set: { if !$0 { pinDialogProfile = nil } }
            )) {
                SecureField("PIN", text: $pinText)
                Button("Login") {
                    if let prof = pinDialogProfile {
                        Task {
                            do {
                                try await authManager.login(user: prof, pin: pinText, deviceName: "iPhone Client")
                                pinDialogProfile = nil
                            } catch {
                                authViewModel.errorMessage = error.localizedDescription
                            }
                        }
                    }
                }
                Button("Cancel", role: .cancel) {
                    pinDialogProfile = nil
                }
            } message: {
                if let p = pinDialogProfile {
                    Text("Enter the PIN for \(p.name)")
                }
            }
            .task {
                if authViewModel.profiles.isEmpty {
                    await authManager.fetchProfiles()
                }
            }
        }
    }
}
