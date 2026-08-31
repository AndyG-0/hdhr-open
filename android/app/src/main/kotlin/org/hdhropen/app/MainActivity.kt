package org.hdhropen.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.navigation.RootMobileScreen
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.theme.ThemeMode
import org.hdhropen.kit.viewmodels.AppEnvironment

@UnstableApi
class MainActivity : ComponentActivity() {
    private lateinit var appEnvironment: AppEnvironment

    // No PiP/background-audio support: once the whole app leaves the
    // foreground there's no legitimate reason to keep the tuner reserved, so
    // release it the same way the in-player close button does. Registered on
    // ProcessLifecycleOwner (not this Activity) so it fires once per real
    // app-background transition rather than on every config change.
    private val processLifecycleObserver = object : DefaultLifecycleObserver {
        override fun onStop(owner: LifecycleOwner) {
            if (::appEnvironment.isInitialized) {
                appEnvironment.playerViewModel.closePlayer()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        appEnvironment = AppEnvironment(applicationContext)
        ProcessLifecycleOwner.get().lifecycle.addObserver(processLifecycleObserver)

        lifecycleScope.launch {
            appEnvironment.authManager.restoreSession()
        }

        setContent {
            val themeMode by appEnvironment.themePreferences.themeMode.collectAsState()
            val useDarkTheme = when (themeMode) {
                ThemeMode.LIGHT -> false
                ThemeMode.DARK -> true
                ThemeMode.SYSTEM -> isSystemInDarkTheme()
            }

            LaunchedEffect(useDarkTheme) {
                WindowInsetsControllerCompat(window, window.decorView).isAppearanceLightStatusBars = !useDarkTheme
            }

            HDHROpenTheme(themeMode = themeMode) {
                RootMobileScreen(appEnvironment = appEnvironment)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        ProcessLifecycleOwner.get().lifecycle.removeObserver(processLifecycleObserver)
        if (::appEnvironment.isInitialized) {
            appEnvironment.playerViewModel.closePlayer()
            appEnvironment.playerEngine.release()
        }
    }
}
