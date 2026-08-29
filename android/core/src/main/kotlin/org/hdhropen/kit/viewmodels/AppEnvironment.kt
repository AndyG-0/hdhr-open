package org.hdhropen.kit.viewmodels

import android.content.Context
import androidx.media3.common.util.UnstableApi
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.AuthManager
import org.hdhropen.kit.networking.ServerDiscovery
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.PlayerEngine

@UnstableApi
class AppEnvironment(
    val context: Context,
    defaultServerURL: String = "http://127.0.0.1:8000"
) {
    val serverDiscovery = ServerDiscovery(context, defaultServerURL)
    val apiClient = APIClient(baseURL = serverDiscovery.serverURLString.value)
    val authManager = AuthManager(apiClient, context)
    val watchSessionManager = WatchSessionManager(apiClient)
    val playerEngine = PlayerEngine(context)

    val guideViewModel = GuideViewModel(apiClient)
    val recordingsViewModel = RecordingsViewModel(apiClient)
    val playerViewModel = PlayerViewModel(apiClient, watchSessionManager, playerEngine)
    val tunerViewModel = TunerViewModel(apiClient)
    val settingsViewModel = SettingsViewModel(apiClient)
    val authViewModel = AuthViewModel(authManager)

    fun updateServerURL(url: String) {
        serverDiscovery.setServerURL(url)
        apiClient.baseURL = url
    }
}
