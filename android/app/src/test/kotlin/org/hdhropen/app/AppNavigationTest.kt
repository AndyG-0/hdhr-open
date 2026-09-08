package org.hdhropen.app

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.filled.LiveTv
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SettingsInputAntenna
import org.hdhropen.app.ui.navigation.AppTab
import org.junit.Assert.assertEquals
import org.junit.Test

class AppNavigationTest {

    @Test
    fun testAppTabValuesAndCount() {
        val tabs = AppTab.values()
        assertEquals(4, tabs.size)
        assertEquals(AppTab.GUIDE, tabs[0])
        assertEquals(AppTab.RECORDINGS, tabs[1])
        assertEquals(AppTab.TUNERS, tabs[2])
        assertEquals(AppTab.SETTINGS, tabs[3])
    }

    @Test
    fun testAppTabTitles() {
        assertEquals("Guide", AppTab.GUIDE.title)
        assertEquals("Recordings", AppTab.RECORDINGS.title)
        assertEquals("Tuners", AppTab.TUNERS.title)
        assertEquals("Settings", AppTab.SETTINGS.title)
    }

    @Test
    fun testAppTabIcons() {
        assertEquals(Icons.Default.LiveTv, AppTab.GUIDE.icon)
        assertEquals(Icons.Default.FiberManualRecord, AppTab.RECORDINGS.icon)
        assertEquals(Icons.Default.SettingsInputAntenna, AppTab.TUNERS.icon)
        assertEquals(Icons.Default.Settings, AppTab.SETTINGS.icon)
    }

    @Test
    fun testAppTabValueOf() {
        assertEquals(AppTab.GUIDE, AppTab.valueOf("GUIDE"))
        assertEquals(AppTab.RECORDINGS, AppTab.valueOf("RECORDINGS"))
        assertEquals(AppTab.TUNERS, AppTab.valueOf("TUNERS"))
        assertEquals(AppTab.SETTINGS, AppTab.valueOf("SETTINGS"))
    }
}
