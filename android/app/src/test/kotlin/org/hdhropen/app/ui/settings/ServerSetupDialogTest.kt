package org.hdhropen.app.ui.settings

import android.content.Context
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.hdhropen.app.ui.screens.settings.ServerSetupDialog
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.networking.ServerDiscovery
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
class ServerSetupDialogTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    private val context: Context
        get() = RuntimeEnvironment.getApplication()

    @Test
    fun testServerSetupDialogRendersAndSaves() {
        val serverDiscovery = ServerDiscovery(context, "http://192.168.1.50:8100")
        var savedUrl = ""
        var dismissed = false

        composeTestRule.setContent {
            HDHROpenTheme {
                ServerSetupDialog(
                    serverDiscovery = serverDiscovery,
                    onDismiss = { dismissed = true },
                    onSaveURL = { savedUrl = it }
                )
            }
        }

        // Verify title & labels
        composeTestRule.onNodeWithText("Server Setup").assertIsDisplayed()
        composeTestRule.onNodeWithText("Discovered Servers (LAN)").assertIsDisplayed()
        composeTestRule.onNodeWithText("Test").assertIsDisplayed()
        composeTestRule.onNodeWithText("Save & Connect").assertIsDisplayed()

        // Click Save & Connect
        composeTestRule.onNodeWithText("Save & Connect").performClick()
        assertEquals("http://192.168.1.50:8100", savedUrl)
        assertTrue(dismissed)
    }

    @Test
    fun testServerSetupDialogDismiss() {
        val serverDiscovery = ServerDiscovery(context, "http://192.168.1.50:8100")
        var dismissed = false

        composeTestRule.setContent {
            HDHROpenTheme {
                ServerSetupDialog(
                    serverDiscovery = serverDiscovery,
                    onDismiss = { dismissed = true },
                    onSaveURL = {}
                )
            }
        }

        composeTestRule.onNodeWithContentDescription("Close").performClick()
        assertTrue(dismissed)
    }
}
