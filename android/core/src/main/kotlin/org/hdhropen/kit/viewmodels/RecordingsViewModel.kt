package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.hdhropen.kit.models.AddRecordingRulePayload
import org.hdhropen.kit.models.HDHomeRunDvrInfo
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import org.hdhropen.kit.models.RecordingRuleOptions
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.utilities.Log

enum class RecordingCategoryFilter(val label: String) {
    ALL("All"),
    SHOWS("Shows"),
    MOVIES("Movies"),
    SPORTS("Sports"),
    IN_PROGRESS("In Progress")
}

class RecordingsViewModel(
    private val apiClient: APIClient
) : ViewModel() {
    private val _recordings = MutableStateFlow<List<HDHomeRunRecording>>(emptyList())
    val recordings: StateFlow<List<HDHomeRunRecording>> = _recordings.asStateFlow()

    private val _recordingRules = MutableStateFlow<List<HDHomeRunRecordingRule>>(emptyList())
    val recordingRules: StateFlow<List<HDHomeRunRecordingRule>> = _recordingRules.asStateFlow()

    private val _dvrInfo = MutableStateFlow<HDHomeRunDvrInfo?>(null)
    val dvrInfo: StateFlow<HDHomeRunDvrInfo?> = _dvrInfo.asStateFlow()

    val selectedFilter = MutableStateFlow(RecordingCategoryFilter.ALL)

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    val filteredRecordings: List<HDHomeRunRecording>
        get() {
            val all = _recordings.value
            return when (selectedFilter.value) {
                RecordingCategoryFilter.ALL -> all
                RecordingCategoryFilter.SHOWS -> all.filter {
                    it.categoryType == "shows" || (it.categoryType == null && it.seasonNumber != null)
                }
                RecordingCategoryFilter.MOVIES -> all.filter {
                    it.categoryType == "movies" || it.category?.contains("movie", ignoreCase = true) == true
                }
                RecordingCategoryFilter.SPORTS -> all.filter {
                    it.categoryType == "sports" || it.category?.contains("sport", ignoreCase = true) == true
                }
                RecordingCategoryFilter.IN_PROGRESS -> all.filter { it.isInProgress }
            }
        }

    val inProgressRecordings: List<HDHomeRunRecording>
        get() = _recordings.value.filter { it.isInProgress }

    val completedRecordings: List<HDHomeRunRecording>
        get() = _recordings.value.filter { !it.isInProgress }

    fun loadData() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                val recsDef = async { loadRecordings() }
                val rulesDef = async { loadRules() }
                val infoDef = async { loadDvrInfo() }

                awaitAll(recsDef, rulesDef, infoDef)
            } finally {
                _isLoading.value = false
            }
        }
    }

    suspend fun loadRecordings() {
        try {
            _recordings.value = apiClient.listRecordings()
        } catch (e: Exception) {
            _error.value = e.localizedMessage
            Log.dvr.error("Failed to load recordings: ${e.localizedMessage}")
        }
    }

    suspend fun loadRules() {
        try {
            _recordingRules.value = apiClient.listRecordingRules()
        } catch (e: Exception) {
            Log.dvr.warning("Failed to load rules: ${e.localizedMessage}")
        }
    }

    suspend fun loadDvrInfo() {
        try {
            _dvrInfo.value = apiClient.getDvrInfo()
        } catch (e: Exception) {
            Log.dvr.debug("Failed to load DVR info: ${e.localizedMessage}")
        }
    }

    suspend fun deleteRecording(recording: HDHomeRunRecording) {
        val id = recording.recordingId ?: return
        apiClient.deleteRecording(id)
        _recordings.value = _recordings.value.filter { it.recordingId != id }
    }

    suspend fun deleteRule(ruleId: String) {
        _recordingRules.value = apiClient.deleteRecordingRule(ruleId)
    }

    suspend fun addRecordingRule(payload: AddRecordingRulePayload) {
        _recordingRules.value = apiClient.addRecordingRule(payload)
    }

    suspend fun updateRecordingRule(ruleId: String, payload: AddRecordingRulePayload) {
        _recordingRules.value = apiClient.updateRecordingRule(ruleId, payload)
    }

    // Creates a standalone standing rule from scratch (no backing airing) —
    // used by rules-management screens' "Add Keyword Rule" flow. Mirrors
    // the web client's `HDHomeRunKeywordRuleDialog`: keyword/contains rules
    // are builtin-DVR-only, enforced server-side regardless of `server`.
    suspend fun createKeywordRule(title: String, options: RecordingRuleOptions) {
        val payload = AddRecordingRulePayload(
            seriesId = "auto",
            channel = options.channel,
            title = title,
            titleMatchMode = options.titleMatchMode,
            keywordQuery = options.keywordQuery,
            recentOnly = options.recentOnly,
            startPadding = options.startPadding,
            endPadding = options.endPadding,
            maxEpisodesToKeep = options.maxEpisodesToKeep,
            server = options.server
        )
        addRecordingRule(payload)
    }
}
