package org.hdhropen.app

import androidx.compose.ui.graphics.Color
import org.hdhropen.app.ui.theme.BlueDark
import org.hdhropen.app.ui.theme.BluePrimary
import org.hdhropen.app.ui.theme.DarkBackground
import org.hdhropen.app.ui.theme.DarkSurface
import org.hdhropen.app.ui.theme.GreenActive
import org.hdhropen.app.ui.theme.LightBackground
import org.hdhropen.app.ui.theme.LightSurface
import org.hdhropen.app.ui.theme.RedLive
import org.hdhropen.app.ui.theme.YellowAccent
import org.hdhropen.kit.theme.ThemeMode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class ThemeTest {

    @Test
    fun testThemeModeEnum() {
        val modes = ThemeMode.values()
        assertEquals(3, modes.size)
        assertEquals(ThemeMode.SYSTEM, ThemeMode.valueOf("SYSTEM"))
        assertEquals(ThemeMode.LIGHT, ThemeMode.valueOf("LIGHT"))
        assertEquals(ThemeMode.DARK, ThemeMode.valueOf("DARK"))
    }

    @Test
    fun testBrandColorsNotNull() {
        assertNotNull(BluePrimary)
        assertNotNull(BlueDark)
        assertNotNull(RedLive)
        assertNotNull(YellowAccent)
        assertNotNull(GreenActive)
        assertNotNull(DarkBackground)
        assertNotNull(DarkSurface)
        assertNotNull(LightBackground)
        assertNotNull(LightSurface)

        assertEquals(Color(0xFF2196F3), BluePrimary)
        assertEquals(Color(0xFFE53935), RedLive)
        assertEquals(Color(0xFFFFD54F), YellowAccent)
        assertEquals(Color(0xFF4CAF50), GreenActive)
        assertEquals(Color(0xFF0F0F12), DarkBackground)
        assertEquals(Color(0xFFF5F5F7), LightBackground)
    }
}
