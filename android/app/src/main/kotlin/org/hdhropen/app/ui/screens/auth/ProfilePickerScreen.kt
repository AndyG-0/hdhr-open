package org.hdhropen.app.ui.screens.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.hdhropen.app.ui.theme.*
import org.hdhropen.kit.models.UserProfile
import org.hdhropen.kit.networking.AuthManager
import org.hdhropen.kit.viewmodels.AuthViewModel

@Composable
fun ProfilePickerScreen(
    authManager: AuthManager,
    authViewModel: AuthViewModel
) {
    val profiles by authManager.profiles.collectAsState()
    val isLoading by authManager.isLoading.collectAsState()
    val authError by authManager.authError.collectAsState()
    val showPinEntry by authViewModel.showPinEntry.collectAsState()

    LaunchedEffect(Unit) {
        authManager.fetchProfiles()
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkBackground)
            .padding(24.dp),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.fillMaxWidth().wrapContentHeight()
        ) {
            // App Logo & Title
            Box(
                modifier = Modifier
                    .size(72.dp)
                    .clip(CircleShape)
                    .background(BluePrimary.copy(alpha = 0.2f))
                    .border(2.dp, BluePrimary, CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    Icons.Default.Tv,
                    contentDescription = "Logo",
                    tint = BluePrimary,
                    modifier = Modifier.size(40.dp)
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            Text(
                text = "HDHR Open",
                style = MaterialTheme.typography.titleLarge.copy(
                    fontSize = 28.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary
                )
            )

            Text(
                text = "Who's watching?",
                style = MaterialTheme.typography.bodyLarge.copy(color = TextSecondary)
            )

            Spacer(modifier = Modifier.height(36.dp))

            if (isLoading && profiles.isEmpty()) {
                CircularProgressIndicator(color = BluePrimary)
            } else if (authError != null && profiles.isEmpty()) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = authError ?: "Failed to connect to server.",
                        style = MaterialTheme.typography.bodyMedium.copy(color = RedLive)
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Button(
                        onClick = { authManager.fetchProfiles() },
                        colors = ButtonDefaults.buttonColors(containerColor = DarkSurfaceVariant)
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = "Retry", tint = TextPrimary)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Retry", color = TextPrimary)
                    }
                }
            } else {
                LazyVerticalGrid(
                    columns = GridCells.Adaptive(minSize = 120.dp),
                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                    modifier = Modifier.fillMaxWidth().wrapContentHeight()
                ) {
                    items(profiles) { profile ->
                        ProfileCard(profile = profile, onSelect = {
                            authViewModel.selectProfile(profile)
                        })
                    }
                }
            }
        }

        if (showPinEntry) {
            PINEntryDialog(authViewModel = authViewModel)
        }
    }
}

@Composable
private fun ProfileCard(
    profile: UserProfile,
    onSelect: () -> Unit
) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = DarkSurface),
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(16.dp))
            .clickable { onSelect() }
            .border(1.dp, DarkBorder, RoundedCornerShape(16.dp))
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Box(
                modifier = Modifier
                    .size(64.dp)
                    .clip(CircleShape)
                    .background(DarkSurfaceVariant)
                    .border(1.5.dp, BluePrimary.copy(alpha = 0.5f), CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    Icons.Default.Person,
                    contentDescription = profile.name,
                    tint = TextPrimary,
                    modifier = Modifier.size(36.dp)
                )

                if (profile.hasPin) {
                    Box(
                        modifier = Modifier
                            .align(Alignment.BottomEnd)
                            .size(20.dp)
                            .clip(CircleShape)
                            .background(DarkBackground)
                            .padding(2.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            Icons.Default.Lock,
                            contentDescription = "PIN",
                            tint = YellowAccent,
                            modifier = Modifier.size(12.dp)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Text(
                text = profile.name,
                style = MaterialTheme.typography.titleMedium.copy(
                    fontSize = 15.sp,
                    color = TextPrimary
                ),
                maxLines = 1
            )
        }
    }
}
