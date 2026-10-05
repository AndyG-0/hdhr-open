package org.hdhropen.kit.playback

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Per-device playback preferences - unlike AppSettings (server-synced,
 * household-wide), these describe what *this device* can do and are never
 * sent to the backend.
 */
class PlaybackPreferences(private val context: Context? = null) {
    private val directPlayKey = "org.hdhropen.client.directPlayEnabled"
    private val autoSkipCommercialsKey = "org.hdhropen.client.autoSkipCommercialsEnabled"
    private val prefsName = "hdhr_open_playback_prefs"

    private val prefs: SharedPreferences? by lazy {
        context?.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
    }

    private val _directPlayEnabled = MutableStateFlow(loadDirectPlayEnabled())
    val directPlayEnabled: StateFlow<Boolean> = _directPlayEnabled.asStateFlow()

    private val _autoSkipCommercialsEnabled = MutableStateFlow(loadAutoSkipCommercialsEnabled())
    val autoSkipCommercialsEnabled: StateFlow<Boolean> = _autoSkipCommercialsEnabled.asStateFlow()

    private fun loadDirectPlayEnabled(): Boolean = prefs?.getBoolean(directPlayKey, false) ?: false

    fun setDirectPlayEnabled(enabled: Boolean) {
        _directPlayEnabled.value = enabled
        prefs?.edit()?.putBoolean(directPlayKey, enabled)?.apply()
    }

    private fun loadAutoSkipCommercialsEnabled(): Boolean =
        prefs?.getBoolean(autoSkipCommercialsKey, false) ?: false

    fun setAutoSkipCommercialsEnabled(enabled: Boolean) {
        _autoSkipCommercialsEnabled.value = enabled
        prefs?.edit()?.putBoolean(autoSkipCommercialsKey, enabled)?.apply()
    }
}
