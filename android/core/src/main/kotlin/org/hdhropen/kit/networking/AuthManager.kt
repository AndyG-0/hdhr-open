package org.hdhropen.kit.networking

import android.content.Context
import android.content.SharedPreferences
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
        context?.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
    }

    val isAuthenticated: Boolean
        get() = _currentUser.value != null

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
