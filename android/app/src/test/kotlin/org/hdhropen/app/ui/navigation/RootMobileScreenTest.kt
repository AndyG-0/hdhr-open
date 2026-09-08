package org.hdhropen.app.ui.navigation

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.media3.common.util.UnstableApi
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.CurrentUser
import org.hdhropen.kit.models.UserRole
import org.hdhropen.kit.viewmodels.AppEnvironment
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@UnstableApi
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RootMobileScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    private val context: Context
        get() = RuntimeEnvironment.getApplication()

    @Test
    fun testRootMobileScreenShowsProfilePickerWhenUnauthenticated() {
        val appEnvironment = AppEnvironment(context)

        composeTestRule.setContent {
            HDHROpenTheme {
                RootMobileScreen(appEnvironment = appEnvironment)
            }
        }

        // Profile picker is shown
        composeTestRule.onNodeWithText("Who's watching?").assertIsDisplayed()
    }

    @Test
    fun testRootMobileScreenShowsTabsWhenAuthenticated() {
        val appEnvironment = AppEnvironment(context)
        appEnvironment.authManager.setCurrentUser(
            CurrentUser(
                id = "user-1",
                name = "Test User",
                role = UserRole.ADMIN
            )
        )

        composeTestRule.setContent {
            HDHROpenTheme {
                RootMobileScreen(appEnvironment = appEnvironment)
            }
        }

        // Navigation bar tabs are displayed
        composeTestRule.onNodeWithText("Guide").assertIsDisplayed()
        composeTestRule.onNodeWithText("Recordings").assertIsDisplayed()
        composeTestRule.onNodeWithText("Tuners").assertIsDisplayed()
        composeTestRule.onNodeWithText("Settings").assertIsDisplayed()

        // Tab switching to Tuners
        composeTestRule.onNodeWithText("Tuners").performClick()
        composeTestRule.onNodeWithText("No HDHomeRun tuners found.").assertExists()

        // Tab switching to Settings
        composeTestRule.onNodeWithText("Settings").performClick()
        composeTestRule.onNodeWithText("APPEARANCE").assertExists()
    }
}
