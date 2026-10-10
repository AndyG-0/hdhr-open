package org.hdhropen.kit.networking

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.hdhropen.kit.models.CurrentUser
import org.hdhropen.kit.models.UserProfile
import org.hdhropen.kit.utilities.Log

class AuthManager(
    private val apiClient: APIClient,
    private val context: Context? = null
) {
    private val _currentUser = MutableStateFlow<CurrentUser?>(null)
    val currentUser: StateFlow<CurrentUser?> = _currentUser.asStateFlow()

    private val _profiles = MutableStateFlow<List<UserProfile>>(emptyList())
    val profiles: StateFlow<List<UserProfile>> = _profiles.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _authError = MutableStateFlow<String?>(null)
    val authError: StateFlow<String?> = _authError.asStateFlow()

    private val tokenKey = "org.hdhropen.client.bearerToken"
    private val deviceIdKey = "org.hdhropen.client.deviceId"
    private val prefsName = "hdhr_open_auth_prefs"

    private val prefs: SharedPreferences? by lazy {
        context?.let { buildPrefs(it) }
    }

    private fun buildPrefs(context: Context): SharedPreferences? {
        return try {
            migrateLegacyPrefsIfNeeded(context) ?: createEncryptedPrefs(context)
        } catch (e: Exception) {
            // If this throws (e.g. a corrupted Keystore entry or an
            // unexpected format we don't otherwise detect), fall back to no
            // persisted storage rather than crashing the app - the session
            // simply won't be restored/persisted this run, matching the
            // pre-existing nullable `prefs` contract everywhere else in this
            // class.
            Log.auth.error("Failed to initialize encrypted auth prefs: ${e.localizedMessage}", e)
            null
        }
    }

    private fun createEncryptedPrefs(context: Context): SharedPreferences {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        return EncryptedSharedPreferences.create(
            context,
            prefsName,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    // Pre-fix installs stored the bearer token/device id in a PLAIN
    // (unencrypted) SharedPreferences file at `prefsName`. EncryptedSharedPreferences
    // uses that same file name, but encrypts both key names (AES256_SIV) and
    // values (AES256_GCM) - so simply wrapping the existing file does not
    // throw, it just silently fails to find the old plaintext entries (their
    // key names don't match the encrypted key names it looks up), which
    // would otherwise look exactly like "never logged in" and quietly log
    // existing users out. Detect that case up front by checking the legacy
    // plain file for our known keys, recover the values, delete the
    // plaintext file, and seed a freshly created encrypted store with them -
    // so upgrading preserves the session. Returns null (do the normal
    // encrypted-create path) when there's nothing to migrate, including on
    // a fresh install or an already-migrated device.
    private fun migrateLegacyPrefsIfNeeded(context: Context): SharedPreferences? {
        val legacyPrefs = context.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        if (!legacyPrefs.contains(tokenKey) && !legacyPrefs.contains(deviceIdKey)) return null

        val recoveredToken = legacyPrefs.getString(tokenKey, null)
        val recoveredDeviceId = legacyPrefs.getString(deviceIdKey, null)

        context.deleteSharedPreferences(prefsName)

        Log.auth.info("Migrating auth prefs from plaintext to encrypted storage")
        val encryptedPrefs = createEncryptedPrefs(context)
        encryptedPrefs.edit().apply {
            recoveredToken?.let { putString(tokenKey, it) }
            recoveredDeviceId?.let { putString(deviceIdKey, it) }
        }.apply()
        return encryptedPrefs
    }

    val isAuthenticated: Boolean
        get() = _currentUser.value != null

    fun setCurrentUser(user: CurrentUser?) {
        _currentUser.value = user
    }

    suspend fun restoreSession() {
        prefs?.getString(deviceIdKey, null)?.let { storedDeviceId ->
            apiClient.deviceId = storedDeviceId
        }
        registerDeviceIfNeeded()

        val token = prefs?.getString(tokenKey, null) ?: return
        apiClient.bearerToken = token

        try {
            val user = apiClient.getCurrentUser()
            _currentUser.value = user
            Log.auth.info("Restored session for user: ${user.name} (${user.id})")
        } catch (e: Exception) {
            Log.auth.warning("Session restore failed, clearing token: ${e.localizedMessage}")
            prefs?.edit()?.remove(tokenKey)?.apply()
            apiClient.bearerToken = null
            _currentUser.value = null
        }
    }

    suspend fun registerDeviceIfNeeded(): Boolean {
        return try {
            val result = apiClient.registerDevice()
            prefs?.edit()?.putString(deviceIdKey, result.id)?.apply()
            apiClient.deviceId = result.id
            true
        } catch (e: Exception) {
            Log.auth.warning("Device registration failed: ${e.localizedMessage}")
            false
        }
    }

    suspend fun fetchProfiles() {
        _isLoading.value = true
        _authError.value = null
        try {
            val list = apiClient.listProfiles()
            _profiles.value = list
        } catch (e: Exception) {
            _authError.value = e.localizedMessage
            Log.auth.error("Failed to load profiles: ${e.localizedMessage}", e)
        } finally {
            _isLoading.value = false
        }
    }

    suspend fun login(user: UserProfile, pin: String?, deviceName: String = "Android Mobile Client") {
        _isLoading.value = true
        _authError.value = null
        try {
            if (apiClient.deviceId == null) {
                registerDeviceIfNeeded()
            }

            val loggedInUser = try {
                apiClient.login(userId = user.id, pin = pin, tokenName = deviceName)
            } catch (e: APIError.Unauthorized) {
                if (e.message.contains("device", ignoreCase = true)) {
                    Log.auth.warning("Login failed due to unregistered device, auto-registering and retrying...")
                    val registered = registerDeviceIfNeeded()
                    if (registered) {
                        apiClient.login(userId = user.id, pin = pin, tokenName = deviceName)
                    } else {
                        throw e
                    }
                } else {
                    throw e
                }
            }

            loggedInUser.token?.let { token ->
                prefs?.edit()?.putString(tokenKey, token)?.apply()
                apiClient.bearerToken = token
            }
            _currentUser.value = loggedInUser
            Log.auth.info("Successfully logged in as ${loggedInUser.name}")
        } catch (e: Exception) {
            _authError.value = e.localizedMessage
            throw e
        } finally {
            _isLoading.value = false
        }
    }

    suspend fun logout() {
        try {
            apiClient.logout()
        } catch (e: Exception) {
            Log.auth.debug("Server logout returned: ${e.localizedMessage}")
        }
        prefs?.edit()?.remove(tokenKey)?.apply()
        apiClient.bearerToken = null
        _currentUser.value = null
    }
}
