package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.utilities.Log

// Mirrors RecordingsViewModel's shape. Backs the Discovery tab: fetches
// GET /api/discovery, which returns upcoming guide airings recommended
// from the household's recording history, or a non-personalized
// "New & Notable" fallback (hasProfile == false) when there's no history
// yet. `enabled` reflects the admin's web-only Settings toggle - the
// Discovery tab's visibility is gated on it (there is no Android settings
// UI for this feature, same precedent as sports_extension_enabled).
class DiscoveryViewModel(
    private val apiClient: APIClient
) : ViewModel() {

    private val _items = MutableStateFlow<List<HDHomeRunGuideEntry>>(emptyList())
    val items: StateFlow<List<HDHomeRunGuideEntry>> = _items.asStateFlow()

    private val _hasProfile = MutableStateFlow(false)
    val hasProfile: StateFlow<Boolean> = _hasProfile.asStateFlow()

    private val _enabled = MutableStateFlow(false)
    val enabled: StateFlow<Boolean> = _enabled.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun loadData() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                val response = apiClient.getDiscovery()
                _enabled.value = response.enabled
                _hasProfile.value = response.hasProfile
                _items.value = response.items
            } catch (e: Exception) {
                _error.value = e.localizedMessage
                Log.general.warning("Failed to load discovery: ${e.localizedMessage}")
            } finally {
                _isLoading.value = false
            }
        }
    }
}
