package org.hdhropen.app.ui.settings

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import io.mockk.mockk
import org.hdhropen.app.ui.screens.settings.SettingsScreen
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.AuthManager
import org.hdhropen.kit.networking.ServerDiscovery
import org.hdhropen.kit.playback.PlaybackPreferences
import org.hdhropen.kit.theme.ThemeMode
import org.hdhropen.kit.theme.ThemePreferences
import org.hdhropen.kit.viewmodels.SettingsViewModel
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class SettingsScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    private val context: Context
        get() = RuntimeEnvironment.getApplication()

    @Test
    fun testSettingsScreenRendersAllSections() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val settingsViewModel = SettingsViewModel(apiClient)
        val authManager = AuthManager(apiClient, context)
        val serverDiscovery = ServerDiscovery(context, "http://192.168.1.100:8100")
        val playbackPreferences = PlaybackPreferences(context)
        val themePreferences = ThemePreferences(context)

        composeTestRule.setContent {
            HDHROpenTheme {
                SettingsScreen(
                    settingsViewModel = settingsViewModel,
                    authManager = authManager,
                    serverDiscovery = serverDiscovery,
                    playbackPreferences = playbackPreferences,
                    themePreferences = themePreferences,
                    onUpdateServerURL = {}
                )
            }
        }

        // Header
        composeTestRule.onNodeWithText("Settings").assertIsDisplayed()

        // Section labels
        composeTestRule.onNodeWithText("APPEARANCE").assertIsDisplayed()
        composeTestRule.onNodeWithText("PROFILE").assertIsDisplayed()
        composeTestRule.onNodeWithText("SERVER CONNECTION").assertExists()
        composeTestRule.onNodeWithText("PLAYBACK").assertExists()

        // Theme buttons
        composeTestRule.onNodeWithText("System").assertIsDisplayed()
        composeTestRule.onNodeWithText("Light").assertIsDisplayed()
        composeTestRule.onNodeWithText("Dark").assertIsDisplayed()

        // Theme click
        composeTestRule.onNodeWithText("Dark").performClick()
        assertEquals(ThemeMode.DARK, themePreferences.themeMode.value)

        // Server connection URL
        composeTestRule.onNodeWithText("http://192.168.1.100:8100").assertExists()

        // Direct Play toggle
        composeTestRule.onNodeWithText("Direct Play").assertExists()
    }
}
