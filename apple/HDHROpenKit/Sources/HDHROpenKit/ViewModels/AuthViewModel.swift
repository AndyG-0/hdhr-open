import Foundation

@MainActor
public final class AuthViewModel: ObservableObject {
    @Published public var selectedProfile: UserProfile?
    @Published public var pinInput = ""
    @Published public var errorMessage: String?
    @Published public var isPINPromptVisible = false

    private let authManager: AuthManager

    public init(authManager: AuthManager) {
        self.authManager = authManager
    }

    public var profiles: [UserProfile] {
        authManager.profiles
    }

    public var currentUser: CurrentUser? {
        authManager.currentUser
    }

    public var isAuthenticated: Bool {
        authManager.isAuthenticated
    }

    public func selectProfile(_ profile: UserProfile) {
        selectedProfile = profile
        pinInput = ""
        errorMessage = nil

        if profile.hasPin {
            isPINPromptVisible = true
        } else {
            Task {
                await loginWithoutPIN(profile: profile)
            }
        }
    }

    public func submitPIN() async {
        guard let profile = selectedProfile else { return }
        guard !pinInput.isEmpty else {
            errorMessage = "Please enter your PIN"
            return
        }

        do {
            try await authManager.login(user: profile, pin: pinInput)
            isPINPromptVisible = false
            pinInput = ""
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
            pinInput = ""
        }
    }

    public func cancelPINEntry() {
        isPINPromptVisible = false
        selectedProfile = nil
        pinInput = ""
        errorMessage = nil
    }

    public func appendPINDigit(_ digit: String) {
        guard pinInput.count < 8 else { return }
        pinInput.append(digit)
    }

    public func deletePINDigit() {
        guard !pinInput.isEmpty else { return }
        pinInput.removeLast()
    }

    public func logout() async {
        await authManager.logout()
        selectedProfile = nil
        isPINPromptVisible = false
    }

    private func loginWithoutPIN(profile: UserProfile) async {
        do {
            try await authManager.login(user: profile, pin: nil)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
