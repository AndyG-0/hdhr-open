package org.hdhropen.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import org.hdhropen.kit.theme.ThemeMode

private val DarkColorScheme = darkColorScheme(
    primary = BluePrimary,
    onPrimary = DarkTextPrimary,
    secondary = YellowAccent,
    onSecondary = DarkBackground,
    tertiary = GreenActive,
    background = DarkBackground,
    onBackground = DarkTextPrimary,
    surface = DarkSurface,
    onSurface = DarkTextPrimary,
    surfaceVariant = DarkSurfaceVariant,
    onSurfaceVariant = DarkTextSecondary,
    outline = DarkBorder
)

private val LightColorScheme = lightColorScheme(
    primary = BluePrimary,
    onPrimary = DarkTextPrimary,
    secondary = YellowAccent,
    onSecondary = DarkBackground,
    tertiary = GreenActive,
    background = LightBackground,
    onBackground = LightTextPrimary,
    surface = LightSurface,
    onSurface = LightTextPrimary,
    surfaceVariant = LightSurfaceVariant,
    onSurfaceVariant = LightTextSecondary,
    outline = LightBorder
)

// Material3's ColorScheme only has two text tiers (onSurface/onSurfaceVariant);
// this app's designs use a third, dimmer "muted" tier, so it rides alongside
// MaterialTheme via its own CompositionLocal rather than being force-fit into
// an ill-suited ColorScheme slot.
data class ExtendedColors(val textMuted: Color)

private val LocalExtendedColors = staticCompositionLocalOf { ExtendedColors(textMuted = DarkTextMuted) }

val MaterialTheme.extendedColors: ExtendedColors
    @Composable
    get() = LocalExtendedColors.current

@Composable
fun HDHROpenTheme(themeMode: ThemeMode = ThemeMode.SYSTEM, content: @Composable () -> Unit) {
    val useDarkTheme = when (themeMode) {
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
        ThemeMode.SYSTEM -> isSystemInDarkTheme()
    }
    CompositionLocalProvider(
        LocalExtendedColors provides ExtendedColors(textMuted = if (useDarkTheme) DarkTextMuted else LightTextMuted)
    ) {
        MaterialTheme(
            colorScheme = if (useDarkTheme) DarkColorScheme else LightColorScheme,
            typography = Typography,
            content = content
        )
    }
}
