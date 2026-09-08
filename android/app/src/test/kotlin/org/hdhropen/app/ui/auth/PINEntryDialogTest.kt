package org.hdhropen.app.ui.auth

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.hdhropen.app.ui.screens.auth.PINEntryDialog
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.UserProfile
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.AuthManager
import org.hdhropen.kit.viewmodels.AuthViewModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PINEntryDialogTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    private val context: Context
        get() = RuntimeEnvironment.getApplication()

    @Test
    fun testPINEntryDialogRendersAndHandlesInput() {
        val apiClient = APIClient(baseURL = "http://127.0.0.1:8000")
        val authManager = AuthManager(apiClient, context)
        val authViewModel = AuthViewModel(authManager)

        val profile = UserProfile(id = "user-1", name = "Andy", hasPin = true)
        authViewModel.selectProfile(profile)
        assertTrue(authViewModel.showPinEntry.value)

        composeTestRule.setContent {
            HDHROpenTheme {
                PINEntryDialog(authViewModel = authViewModel)
            }
        }

        // Verify title & profile name
        composeTestRule.onNodeWithText("Enter PIN").assertIsDisplayed()
        composeTestRule.onNodeWithText("Profile: Andy").assertIsDisplayed()

        // Click keypad digits
        composeTestRule.onNodeWithText("1").performClick()
        assertEquals("1", authViewModel.pin.value)

        composeTestRule.onNodeWithText("2").performClick()
        assertEquals("12", authViewModel.pin.value)

        // Delete digit
        composeTestRule.onNodeWithContentDescription("Delete").performClick()
        assertEquals("1", authViewModel.pin.value)

        // Close dialog
        composeTestRule.onNodeWithContentDescription("Close").performClick()
        assertFalse(authViewModel.showPinEntry.value)
    }
}
