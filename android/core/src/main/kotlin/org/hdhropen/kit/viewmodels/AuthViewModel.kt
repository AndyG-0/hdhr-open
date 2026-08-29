package org.hdhropen.kit.viewmodels

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.hdhropen.kit.models.UserProfile
import org.hdhropen.kit.networking.AuthManager

class AuthViewModel(
    private val authManager: AuthManager
) : ViewModel() {
    private val _selectedProfile = MutableStateFlow<UserProfile?>(null)
    val selectedProfile: StateFlow<UserProfile?> = _selectedProfile.asStateFlow()

    private val _pin = MutableStateFlow("")
    val pin: StateFlow<String> = _pin.asStateFlow()

    private val _showPinEntry = MutableStateFlow(false)
    val showPinEntry: StateFlow<Boolean> = _showPinEntry.asStateFlow()

    private val _isSubmitting = MutableStateFlow(false)
    val isSubmitting: StateFlow<Boolean> = _isSubmitting.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun selectProfile(profile: UserProfile) {
        _selectedProfile.value = profile
        _pin.value = ""
        _error.value = null
        if (profile.hasPin) {
            _showPinEntry.value = true
        } else {
            login(profile, null)
        }
    }

    fun appendPinDigit(digit: String) {
        if (_pin.value.length < 4) {
            _pin.value = _pin.value + digit
            if (_pin.value.length == 4) {
                _selectedProfile.value?.let { profile ->
                    login(profile, _pin.value)
                }
            }
        }
    }

    fun deletePinDigit() {
        if (_pin.value.isNotEmpty()) {
            _pin.value = _pin.value.dropLast(1)
        }
    }

    fun clearPin() {
        _pin.value = ""
    }

    fun dismissPinEntry() {
        _showPinEntry.value = false
        _pin.value = ""
        _selectedProfile.value = null
        _error.value = null
    }

    fun login(profile: UserProfile, enteredPin: String?) {
        viewModelScope.launch {
            _isSubmitting.value = true
            _error.value = null
            try {
                authManager.login(user = profile, pin = enteredPin)
                _showPinEntry.value = false
                _pin.value = ""
                _selectedProfile.value = null
            } catch (e: Exception) {
                _error.value = e.localizedMessage ?: "Login failed"
                _pin.value = ""
            } finally {
                _isSubmitting.value = false
            }
        }
    }
}
