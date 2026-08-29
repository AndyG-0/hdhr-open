package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.hdhropen.kit.models.AppSettings
import org.hdhropen.kit.models.HDHomeRunTranscodePreset
import org.hdhropen.kit.models.HWAccelDiagnostics
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.utilities.Log

class SettingsViewModel(
    private val apiClient: APIClient
) : ViewModel() {
    private val _settings = MutableStateFlow<AppSettings?>(null)
    val settings: StateFlow<AppSettings?> = _settings.asStateFlow()

    private val _transcodePresets = MutableStateFlow<List<HDHomeRunTranscodePreset>>(emptyList())
    val transcodePresets: StateFlow<List<HDHomeRunTranscodePreset>> = _transcodePresets.asStateFlow()

    private val _hwAccelDiagnostics = MutableStateFlow<HWAccelDiagnostics?>(null)
    val hwAccelDiagnostics: StateFlow<HWAccelDiagnostics?> = _hwAccelDiagnostics.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun loadData() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                val presetsDef = async {
                    try {
                        _transcodePresets.value = apiClient.getTranscodePresets()
                    } catch (e: Exception) {
                        Log.general.warning("Failed to load presets: ${e.localizedMessage}")
                    }
                }
                val diagDef = async {
                    try {
                        _hwAccelDiagnostics.value = apiClient.getHWAccelDiagnostics()
                    } catch (e: Exception) {
                        // Diagnostics optional
                    }
                }
                val settingsDef = async {
                    try {
                        _settings.value = apiClient.getSettings()
                    } catch (e: Exception) {
                        // Settings optional
                    }
                }
                awaitAll(presetsDef, diagDef, settingsDef)
            } finally {
                _isLoading.value = false
            }
        }
    }
}
