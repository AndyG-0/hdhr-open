import Foundation
import Security

@MainActor
public final class AuthManager: ObservableObject {
    @Published public private(set) var currentUser: CurrentUser?
    @Published public private(set) var profiles: [UserProfile] = []
    @Published public private(set) var isLoading: Bool = false
    @Published public private(set) var authError: String?

    private let apiClient: APIClient
    private let tokenKey = "org.hdhropen.client.bearerToken"
    private let userIdKey = "org.hdhropen.client.userId"
    private let deviceIdKey = "org.hdhropen.client.deviceId"

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public var isAuthenticated: Bool {
        currentUser != nil
    }

    public func restoreSession() async {
        await registerDeviceIfNeeded()

        guard let token = loadKeychainString(key: tokenKey) else {
            return
        }

        await apiClient.setBearerToken(token)
        do {
            let user = try await apiClient.getCurrentUser()
            self.currentUser = user
            Log.auth.info("Restored session for user: \(user.name) (\(user.id))")
        } catch {
            Log.auth.warning("Session restore failed, clearing token: \(error.localizedDescription)")
            clearKeychain(key: tokenKey)
            await apiClient.setBearerToken(nil)
        }
    }

    /// The backend keys every login attempt off a device cookie (`get_current_device`
    /// never auto-provisions one), so a device must be registered before login can
    /// ever succeed. Idempotent server-side — safe to call on every launch and every
    /// server-address change, not just the first time.
    private func registerDeviceIfNeeded() async {
        do {
            _ = try await apiClient.registerDevice()
        } catch {
            Log.auth.warning("Device registration failed: \(error.localizedDescription)")
        }
    }

    public func fetchProfiles() async {
        isLoading = true
        authError = nil
        do {
            let list = try await apiClient.listProfiles()
            self.profiles = list
        } catch {
            authError = error.localizedDescription
            Log.auth.error("Failed to load profiles: \(error.localizedDescription)")
        }
        isLoading = false
    }

    public func login(user: UserProfile, pin: String?, deviceName: String = "Apple TV Client") async throws {
        isLoading = true
        authError = nil
        defer { isLoading = false }

        do {
            let loggedInUser = try await apiClient.login(userId: user.id, pin: pin, tokenName: deviceName)
            if let token = loggedInUser.token {
                saveKeychainString(key: tokenKey, value: token)
                await apiClient.setBearerToken(token)
            }
            self.currentUser = loggedInUser
            Log.auth.info("Successfully logged in as \(loggedInUser.name)")
        } catch {
            authError = error.localizedDescription
            throw error
        }
    }

    public func logout() async {
        do {
            try await apiClient.logout()
        } catch {
            Log.auth.debug("Server logout returned: \(error.localizedDescription)")
        }
        clearKeychain(key: tokenKey)
        await apiClient.setBearerToken(nil)
        self.currentUser = nil
    }

    // MARK: - Keychain Helpers

    private func saveKeychainString(key: String, value: String) {
        guard let data = value.data(using: .utf8) else { return }
        clearKeychain(key: key)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]
        SecItemAdd(query as CFDictionary, nil)
    }

    private func loadKeychainString(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var dataTypeRef: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &dataTypeRef)
        guard status == errSecSuccess, let data = dataTypeRef as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func clearKeychain(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key
        ]
        SecItemDelete(query as CFDictionary)
    }
}
