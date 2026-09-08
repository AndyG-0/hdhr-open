package org.hdhropen.app.ui.auth

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import org.hdhropen.app.ui.screens.auth.ProfilePickerScreen
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.UserProfile
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.AuthManager
import org.hdhropen.kit.networking.ServerDiscovery
import org.hdhropen.kit.viewmodels.AuthViewModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ProfilePickerScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    private val context: Context
        get() = RuntimeEnvironment.getApplication()

    @Test
    fun testProfilePickerRendersProfilesAndHandlesSelection() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val profileWithPin = UserProfile(id = "user-1", name = "Adult User", hasPin = true)
        val profileNoPin = UserProfile(id = "user-2", name = "Kids Profile", hasPin = false)
        coEvery { apiClient.listProfiles() } returns listOf(profileWithPin, profileNoPin)

        val authManager = AuthManager(apiClient, context)
        runBlocking { authManager.fetchProfiles() }
        val authViewModel = AuthViewModel(authManager)
        val serverDiscovery = ServerDiscovery(context, "http://127.0.0.1:8000")

        composeTestRule.setContent {
            HDHROpenTheme {
                ProfilePickerScreen(
                    authManager = authManager,
                    authViewModel = authViewModel,
                    serverDiscovery = serverDiscovery,
                    onUpdateServerURL = {}
                )
            }
        }

        // Verify headers
        composeTestRule.onNodeWithText("HDHR Open").assertIsDisplayed()
        composeTestRule.onNodeWithText("Who's watching?").assertIsDisplayed()

        // Verify profile names
        composeTestRule.onNodeWithText("Adult User").assertIsDisplayed()
        composeTestRule.onNodeWithText("Kids Profile").assertIsDisplayed()

        // Clicking profile with PIN opens PIN entry
        composeTestRule.onNodeWithText("Adult User").performClick()
        assertTrue(authViewModel.showPinEntry.value)
        assertEquals("Adult User", authViewModel.selectedProfile.value?.name)
    }

    @Test
    fun testServerSettingsButtonOpensDialog() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val authManager = AuthManager(apiClient, context)
        val authViewModel = AuthViewModel(authManager)
        val serverDiscovery = ServerDiscovery(context, "http://127.0.0.1:8000")

        composeTestRule.setContent {
            HDHROpenTheme {
                ProfilePickerScreen(
                    authManager = authManager,
                    authViewModel = authViewModel,
                    serverDiscovery = serverDiscovery,
                    onUpdateServerURL = {}
                )
            }
        }

        composeTestRule.onNodeWithContentDescription("Server Settings").performClick()
        composeTestRule.onNodeWithText("Server Setup").assertIsDisplayed()
    }
}
