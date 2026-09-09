package org.hdhropen.app.ui.screens.player

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import org.hdhropen.app.ui.theme.YellowAccent

@Composable
fun CaptionsOverlay(
    activeCaptionText: String?,
    isCaptionsEnabled: Boolean,
    showControls: Boolean,
    modifier: Modifier = Modifier
) {
    if (isCaptionsEnabled && !activeCaptionText.isNullOrEmpty()) {
        Box(
            modifier = modifier
                .padding(bottom = if (showControls) 120.dp else 40.dp)
                .padding(horizontal = 24.dp)
                .clip(RoundedCornerShape(6.dp))
                .background(Color.Black.copy(alpha = 0.75f))
                .padding(horizontal = 12.dp, vertical = 6.dp)
        ) {
            Text(
                text = activeCaptionText,
                style = MaterialTheme.typography.bodyMedium.copy(
                    color = YellowAccent,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center
                )
            )
        }
    }
}
