package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.hdhropen.kit.models.HDHomeRunTuner
import org.hdhropen.kit.models.HDHomeRunTunerInfo
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.utilities.Log

class TunerViewModel(
    private val apiClient: APIClient
) : ViewModel() {
    private val _tuners = MutableStateFlow<List<HDHomeRunTuner>>(emptyList())
    val tuners: StateFlow<List<HDHomeRunTuner>> = _tuners.asStateFlow()

    private val _tunerInfo = MutableStateFlow<HDHomeRunTunerInfo?>(null)
    val tunerInfo: StateFlow<HDHomeRunTunerInfo?> = _tunerInfo.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private var pollingJob: Job? = null

    fun loadData() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                _tuners.value = apiClient.getTunerStatus()
                _tunerInfo.value = apiClient.getTunerInfo()
            } catch (e: Exception) {
                _error.value = e.localizedMessage
                Log.general.error("Failed to load tuner info: ${e.localizedMessage}")
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun startPolling(intervalMs: Long = 3000) {
        stopPolling()
        pollingJob = viewModelScope.launch {
            while (isActive) {
                try {
                    _tuners.value = apiClient.getTunerStatus()
                } catch (e: Exception) {
                    // Ignore transient errors while polling
                }
                delay(intervalMs)
            }
        }
    }

    fun stopPolling() {
        pollingJob?.cancel()
        pollingJob = null
    }

    override fun onCleared() {
        super.onCleared()
        stopPolling()
    }
}
