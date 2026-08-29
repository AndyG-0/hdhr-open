package org.hdhropen.kit.playback

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

class CaptionController {
    private val _cues = MutableStateFlow<List<CaptionCue>>(emptyList())
    val cues: StateFlow<List<CaptionCue>> = _cues.asStateFlow()

    private val _isEnabled = MutableStateFlow(false)
    val isEnabled: StateFlow<Boolean> = _isEnabled.asStateFlow()

    private val _activeCueText = MutableStateFlow<String?>(null)
    val activeCueText: StateFlow<String?> = _activeCueText.asStateFlow()

    fun setCues(newCues: List<CaptionCue>) {
        _cues.value = newCues
    }

    fun toggleEnabled() {
        _isEnabled.value = !_isEnabled.value
        if (!_isEnabled.value) {
            _activeCueText.value = null
        }
    }

    fun setEnabled(enabled: Boolean) {
        _isEnabled.value = enabled
        if (!enabled) {
            _activeCueText.value = null
        }
    }

    fun updatePlaybackTime(currentTime: Double) {
        if (!_isEnabled.value) {
            _activeCueText.value = null
            return
        }

        val matchingCue = _cues.value.firstOrNull { it.contains(currentTime) }
        _activeCueText.value = matchingCue?.text
    }

    fun reset() {
        _cues.value = emptyList()
        _activeCueText.value = null
    }
}
