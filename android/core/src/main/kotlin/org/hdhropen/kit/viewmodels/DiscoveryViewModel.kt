package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.utilities.Log

enum class DiscoveryBucketFilter(val bucket: String?, val label: String) {
    ALL(null, "All"),
    SHOWS("shows", "Shows"),
    MOVIES("movies", "Movies"),
    SPORTS("sports", "Sports")
}

// Mirrors RecordingsViewModel's shape. Backs the Discovery tab: fetches
// GET /api/discovery, which returns upcoming guide airings recommended
// from the household's recording history, or a non-personalized
// "New & Notable" fallback (hasProfile == false) when there's no history
// yet. `enabled` reflects the admin's web-only Settings toggle - the
// Discovery tab's visibility is gated on it (there is no Android settings
// UI for this feature, same precedent as sports_extension_enabled).
class DiscoveryViewModel(
    private val apiClient: APIClient,
    private val externalScope: CoroutineScope? = null
) : ViewModel() {

    // Defers to `externalScope` (e.g. a test's `TestScope`) when supplied, so
    // loadData()'s coroutine is a structured child of that scope instead of the
    // framework's own `viewModelScope` - mirrors AIAssistantViewModel.
    private val workScope: CoroutineScope
        get() = externalScope ?: viewModelScope

    private val _items = MutableStateFlow<List<HDHomeRunGuideEntry>>(emptyList())
    val items: StateFlow<List<HDHomeRunGuideEntry>> = _items.asStateFlow()

    private val _filter = MutableStateFlow(DiscoveryBucketFilter.ALL)
    val filter: StateFlow<DiscoveryBucketFilter> = _filter.asStateFlow()

    // Local filter over the single fetch above - selecting a bucket never
    // triggers a second network call.
    val filteredItems: StateFlow<List<HDHomeRunGuideEntry>> = combine(_items, _filter) { items, filter ->
        if (filter.bucket == null) items else items.filter { it.bucket == filter.bucket }
    }.stateIn(workScope, SharingStarted.Eagerly, emptyList())

    fun setFilter(filter: DiscoveryBucketFilter) {
        _filter.value = filter
    }

    private val _hasProfile = MutableStateFlow(false)
    val hasProfile: StateFlow<Boolean> = _hasProfile.asStateFlow()

    private val _enabled = MutableStateFlow(false)
    val enabled: StateFlow<Boolean> = _enabled.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun loadData() {
        workScope.launch {
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
