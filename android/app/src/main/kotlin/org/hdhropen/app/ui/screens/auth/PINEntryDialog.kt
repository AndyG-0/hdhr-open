package org.hdhropen.app.ui.screens.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Backspace
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.viewmodels.AuthViewModel

@Composable
fun PINEntryDialog(
    authViewModel: AuthViewModel
) {
    val selectedProfile by authViewModel.selectedProfile.collectAsState()
    val pin by authViewModel.pin.collectAsState()
    val error by authViewModel.error.collectAsState()
    val isSubmitting by authViewModel.isSubmitting.collectAsState()

    Dialog(onDismissRequest = { authViewModel.dismissPinEntry() }) {
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = MaterialTheme.colorScheme.surface,
            modifier = Modifier.fillMaxWidth().padding(16.dp)
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                // Header with close button
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Enter PIN",
                        style = MaterialTheme.typography.titleMedium.copy(color = MaterialTheme.colorScheme.onSurface)
                    )
                    IconButton(onClick = { authViewModel.dismissPinEntry() }) {
                        Icon(Icons.Default.Close, contentDescription = "Close", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }

                Spacer(modifier = Modifier.height(8.dp))

                Text(
                    text = "Profile: ${selectedProfile?.name ?: ""}",
                    style = MaterialTheme.typography.bodyMedium.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
                )

                Spacer(modifier = Modifier.height(20.dp))

                // PIN Dots
                Row(
                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    for (i in 0 until 4) {
                        val isFilled = i < pin.length
                        Box(
                            modifier = Modifier
                                .size(16.dp)
                                .clip(CircleShape)
                                .background(if (isFilled) BluePrimary else MaterialTheme.colorScheme.surfaceVariant)
                                .border(1.dp, if (isFilled) BluePrimary else MaterialTheme.colorScheme.outline, CircleShape)
                        )
                    }
                }

                if (error != null) {
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = error ?: "",
                        style = MaterialTheme.typography.labelMedium.copy(color = RedLive)
                    )
                }

                Spacer(modifier = Modifier.height(24.dp))

                if (isSubmitting) {
                    CircularProgressIndicator(color = BluePrimary, modifier = Modifier.size(36.dp))
                } else {
                    // Numeric keypad (3x4 grid)
                    val keypad = listOf(
                        listOf("1", "2", "3"),
                        listOf("4", "5", "6"),
                        listOf("7", "8", "9"),
                        listOf("", "0", "DEL")
                    )

                    for (row in keypad) {
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(16.dp),
                            modifier = Modifier.padding(vertical = 6.dp)
                        ) {
                            for (key in row) {
                                if (key.isEmpty()) {
                                    Spacer(modifier = Modifier.size(60.dp))
                                } else if (key == "DEL") {
                                    Box(
                                        modifier = Modifier
                                            .size(60.dp)
                                            .clip(CircleShape)
                                            .background(MaterialTheme.colorScheme.surfaceVariant)
                                            .clickable { authViewModel.deletePinDigit() },
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Icon(Icons.Default.Backspace, contentDescription = "Delete", tint = MaterialTheme.colorScheme.onSurface)
                                    }
                                } else {
                                    Box(
                                        modifier = Modifier
                                            .size(60.dp)
                                            .clip(CircleShape)
                                            .background(MaterialTheme.colorScheme.surfaceVariant)
                                            .clickable { authViewModel.appendPinDigit(key) },
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Text(
                                            text = key,
                                            style = MaterialTheme.typography.titleMedium.copy(
                                                color = MaterialTheme.colorScheme.onSurface,
                                                fontSize = 22.sp,
                                                fontWeight = FontWeight.Bold
                                            )
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
