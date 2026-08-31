package org.hdhropen.kit.theme

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

enum class ThemeMode {
    LIGHT,
    DARK,
    SYSTEM,
}

/**
 * Per-device display preference - unlike AppSettings (server-synced,
 * household-wide), this describes what *this device* should render and is
 * never sent to the backend.
 */
class ThemePreferences(private val context: Context? = null) {
    private val themeModeKey = "org.hdhropen.client.themeMode"
    private val prefsName = "hdhr_open_theme_prefs"

    private val prefs: SharedPreferences? by lazy {
        context?.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
    }

    private val _themeMode = MutableStateFlow(loadThemeMode())
    val themeMode: StateFlow<ThemeMode> = _themeMode.asStateFlow()

    private fun loadThemeMode(): ThemeMode {
        val stored = prefs?.getString(themeModeKey, null) ?: return ThemeMode.SYSTEM
        return runCatching { ThemeMode.valueOf(stored) }.getOrDefault(ThemeMode.SYSTEM)
    }

    fun setThemeMode(mode: ThemeMode) {
        _themeMode.value = mode
        prefs?.edit()?.putString(themeModeKey, mode.name)?.apply()
    }
}
