package org.hdhropen.app.ui.navigation

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Antenna
import androidx.compose.material.icons.filled.FiberManualRecord
import androidx.compose.material.icons.filled.LiveTv
import androidx.compose.material.icons.filled.Settings
import androidx.compose.ui.graphics.vector.ImageVector

enum class AppTab(val title: String, val icon: ImageVector) {
    GUIDE("Guide", Icons.Default.LiveTv),
    RECORDINGS("Recordings", Icons.Default.FiberManualRecord),
    TUNERS("Tuners", Icons.Default.Antenna),
    SETTINGS("Settings", Icons.Default.Settings)
}
