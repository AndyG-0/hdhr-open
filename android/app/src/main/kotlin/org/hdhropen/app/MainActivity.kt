package org.hdhropen.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.util.UnstableApi
import kotlinx.coroutines.launch
import org.hdhropen.app.ui.navigation.RootMobileScreen
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.viewmodels.AppEnvironment

@UnstableApi
class MainActivity : ComponentActivity() {
    private lateinit var appEnvironment: AppEnvironment

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        appEnvironment = AppEnvironment(applicationContext)

        lifecycleScope.launch {
            appEnvironment.authManager.restoreSession()
        }

        setContent {
            HDHROpenTheme {
                RootMobileScreen(appEnvironment = appEnvironment)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (::appEnvironment.isInitialized) {
            appEnvironment.playerEngine.release()
        }
    }
}
