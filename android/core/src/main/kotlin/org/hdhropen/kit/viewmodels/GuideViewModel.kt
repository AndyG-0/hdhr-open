package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.utilities.Log
import org.hdhropen.kit.utilities.RecordingRuleMatcher

class GuideViewModel(
    val apiClient: APIClient
) : ViewModel() {
    private val _channels = MutableStateFlow<List<HDHomeRunChannel>>(emptyList())
    val channels: StateFlow<List<HDHomeRunChannel>> = _channels.asStateFlow()

    private val _fullGuide = MutableStateFlow<List<HDHomeRunFullGuideChannel>>(emptyList())
    val fullGuide: StateFlow<List<HDHomeRunFullGuideChannel>> = _fullGuide.asStateFlow()

    private val _recordingRules = MutableStateFlow<List<HDHomeRunRecordingRule>>(emptyList())
    val recordingRules: StateFlow<List<HDHomeRunRecordingRule>> = _recordingRules.asStateFlow()

    private val _favoriteChannels = MutableStateFlow<Set<String>>(emptySet())
    val favoriteChannels: StateFlow<Set<String>> = _favoriteChannels.asStateFlow()

    val filterOnlyFavorites = MutableStateFlow(false)

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _guideAvailable = MutableStateFlow(false)
    val guideAvailable: StateFlow<Boolean> = _guideAvailable.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    val displayedChannels: List<HDHomeRunChannel>
        get() {
            val all = _channels.value
            val favs = _favoriteChannels.value
            if (filterOnlyFavorites.value && favs.isNotEmpty()) {
                return all.filter { favs.contains(it.channelNumber) }
            }
            return all
        }

    fun loadData() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                val channelsDef = async { loadChannels() }
                val guideDef = async { loadGuide() }
                val favsDef = async { loadFavorites() }
                val rulesDef = async { loadRules() }

                awaitAll(channelsDef, guideDef, favsDef, rulesDef)
            } finally {
                _isLoading.value = false
            }
        }
    }

    suspend fun loadChannels() {
        try {
            val resp = apiClient.getChannels()
            _channels.value = resp.channels
            _guideAvailable.value = resp.guideAvailable
        } catch (e: Exception) {
            _error.value = e.localizedMessage
            Log.general.error("Failed to load channels: ${e.localizedMessage}")
        }
    }

    suspend fun loadGuide() {
        try {
            val guide = apiClient.getGuide()
            _fullGuide.value = guide
        } catch (e: Exception) {
            Log.general.warning("Failed to load full guide: ${e.localizedMessage}")
        }
    }

    suspend fun loadFavorites() {
        try {
            val integration = apiClient.getNetworkIntegration("hdhomerun")
            val favsElement = integration.settings["favorite_channels"]
            if (favsElement is JsonArray) {
                val favs = favsElement.mapNotNull {
                    if (it is JsonPrimitive && it.isString) it.content else null
                }.toSet()
                _favoriteChannels.value = favs
            }
        } catch (e: Exception) {
            // Favoriting is optional
        }
    }

    suspend fun loadRules() {
        try {
            _recordingRules.value = apiClient.listRecordingRules()
        } catch (e: Exception) {
            Log.dvr.warning("Failed to load recording rules: ${e.localizedMessage}")
        }
    }

    fun toggleFavorite(channelNumber: String) {
        viewModelScope.launch {
            val current = _favoriteChannels.value.toMutableSet()
            if (current.contains(channelNumber)) {
                current.remove(channelNumber)
            } else {
                current.add(channelNumber)
            }
            _favoriteChannels.value = current

            try {
                val jsonArray = JsonArray(current.map { JsonPrimitive(it) })
                apiClient.updateNetworkIntegration(
                    type = "hdhomerun",
                    settings = mapOf("favorite_channels" to jsonArray)
                )
            } catch (e: Exception) {
                Log.general.error("Failed to save favorite channels: ${e.localizedMessage}")
            }
        }
    }

    fun findRule(channelNumber: String?, airing: HDHomeRunGuideEntry?): HDHomeRunRecordingRule? {
        return RecordingRuleMatcher.findMatchingRule(_recordingRules.value, channelNumber, airing)
    }

    suspend fun recordEpisode(
        seriesId: String? = null,
        channelNumber: String? = null,
        start: Double? = null,
        options: RecordingRuleOptions? = null
    ) {
        val payload = AddRecordingRulePayload(
            seriesId = if (seriesId.isNullOrEmpty()) "auto" else seriesId,
            dateTime = start,
            channel = options?.channel ?: channelNumber,
            title = options?.title,
            titleMatchMode = options?.titleMatchMode,
            keywordQuery = options?.keywordQuery,
            recentOnly = options?.recentOnly,
            startPadding = options?.startPadding,
            endPadding = options?.endPadding,
            maxEpisodesToKeep = options?.maxEpisodesToKeep,
            server = options?.server
        )
        _recordingRules.value = apiClient.addRecordingRule(payload)
        loadRules()
    }

    suspend fun recordSeries(
        seriesId: String,
        channelNumber: String? = null,
        options: RecordingRuleOptions? = null
    ) {
        val payload = AddRecordingRulePayload(
            seriesId = seriesId.ifEmpty { "auto" },
            channel = options?.channel ?: channelNumber,
            title = options?.title,
            titleMatchMode = options?.titleMatchMode,
            keywordQuery = options?.keywordQuery,
            recentOnly = options?.recentOnly ?: false,
            startPadding = options?.startPadding,
            endPadding = options?.endPadding,
            maxEpisodesToKeep = options?.maxEpisodesToKeep,
            server = options?.server
        )
        _recordingRules.value = apiClient.addRecordingRule(payload)
        loadRules()
    }

    suspend fun updateRule(
        ruleId: String,
        isSeries: Boolean,
        options: RecordingRuleOptions? = null,
        seriesId: String? = null,
        start: Double? = null,
        channelNumber: String? = null
    ) {
        val payload = AddRecordingRulePayload(
            seriesId = if (seriesId.isNullOrEmpty()) "auto" else seriesId,
            dateTime = if (isSeries) null else start,
            channel = options?.channel ?: channelNumber,
            title = options?.title,
            titleMatchMode = options?.titleMatchMode,
            keywordQuery = options?.keywordQuery,
            recentOnly = if (isSeries) (options?.recentOnly ?: false) else null,
            startPadding = options?.startPadding,
            endPadding = options?.endPadding,
            maxEpisodesToKeep = options?.maxEpisodesToKeep,
            server = options?.server
        )
        _recordingRules.value = apiClient.updateRecordingRule(ruleId, payload)
        loadRules()
    }

    suspend fun cancelRule(ruleId: String) {
        _recordingRules.value = apiClient.deleteRecordingRule(ruleId)
        loadRules()
    }

    fun getAirings(channelNumber: String): List<HDHomeRunGuideEntry> {
        val full = _fullGuide.value.firstOrNull { it.channelNumber == channelNumber }
        if (full != null && full.airings.isNotEmpty()) {
            return full.airings
        }

        val ch = _channels.value.firstOrNull { it.channelNumber == channelNumber }
        if (ch != null) {
            val list = mutableListOf<HDHomeRunGuideEntry>()
            ch.now?.let { list.add(it) }
            ch.next?.let { list.add(it) }
            return list
        }
        return emptyList()
    }
}
