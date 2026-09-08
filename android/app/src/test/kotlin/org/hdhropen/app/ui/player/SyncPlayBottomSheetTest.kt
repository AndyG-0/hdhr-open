package org.hdhropen.app.ui.player

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import io.mockk.*
import kotlinx.coroutines.flow.MutableStateFlow
import org.hdhropen.app.ui.screens.player.SyncPlayBottomSheet
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.CaptionController
import org.hdhropen.kit.playback.PlayerEngine
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1000dp")
class SyncPlayBottomSheetTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    private var activeVm: PlayerViewModel? = null

    @After
    fun tearDown() {
        activeVm?.closePlayer()
        activeVm = null
    }

    private fun createMockPlayerViewModel(): PlayerViewModel {
        val apiClient = APIClient("http://localhost:8000")
        val watchSessionManager = mockk<WatchSessionManager>(relaxed = true)
        val playerEngine = PlayerEngine()
        val captionController = CaptionController()

        val vm = spyk(PlayerViewModel(apiClient, watchSessionManager, playerEngine, captionController))
        activeVm = vm
        return vm
    }

    @Test
    fun testSyncPlayBottomSheetDisconnectedState() {
        val vm = createMockPlayerViewModel()
        var dismissed = false

        composeTestRule.setContent {
            HDHROpenTheme {
                SyncPlayBottomSheet(
                    playerViewModel = vm,
                    onDismiss = { dismissed = true }
                )
            }
        }

        composeTestRule.onNodeWithText("SyncPlay Watch Party").assertExists()
        composeTestRule.onNodeWithText("Your Display Name").assertExists()
        composeTestRule.onNodeWithText("Room Code").assertExists()
        composeTestRule.onNodeWithText("Join Party").assertExists()
        composeTestRule.onNodeWithText("Create New Watch Party").assertExists()

        // Close button
        composeTestRule.onNodeWithContentDescription("Close").performClick()
        assertTrue(dismissed)
    }

    @Test
    fun testSyncPlayBottomSheetJoinAndCreateActions() {
        val vm = createMockPlayerViewModel()
        every { vm.joinSyncPlayRoom(any(), any(), any()) } answers {
            val cb = thirdArg<(Result<Unit>) -> Unit>()
            cb(Result.success(Unit))
        }
        every { vm.createSyncPlayRoom(any(), any()) } answers {
            val cb = secondArg<(Result<Unit>) -> Unit>()
            cb(Result.failure(RuntimeException("Server room limit reached")))
        }

        composeTestRule.setContent {
            HDHROpenTheme {
                SyncPlayBottomSheet(
                    playerViewModel = vm,
                    onDismiss = {}
                )
            }
        }

        // Enter 6-char room code
        composeTestRule.onNodeWithText("Room Code").performTextInput("ABCDEF")
        composeTestRule.onNodeWithText("Join Party").performClick()
        verify { vm.joinSyncPlayRoom("ABCDEF", any(), any()) }

        // Click create room (which fails in our mock)
        composeTestRule.onNodeWithText("Create New Watch Party").performClick()
        verify { vm.createSyncPlayRoom(any(), any()) }
        // Error banner should be displayed
        composeTestRule.onNodeWithText("Server room limit reached").assertIsDisplayed()
    }

    @Test
    fun testSyncPlayBottomSheetConnectedActiveRoomState() {
        val vm = createMockPlayerViewModel()
        var dismissed = false

        val room = SyncPlayRoom(
            roomCode = "PARTY1",
            hostSessionId = "sess-host",
            createdAt = 1000.0,
            content = SyncPlayContent(
                type = "channel",
                title = "Super Bowl LIX",
                channelNumber = "7.1"
            ),
            playbackState = SyncPlayPlaybackState(isPlaying = true, position = 120.0),
            participants = listOf(
                SyncPlayParticipant(
                    sessionId = "sess-me",
                    userName = "Android User",
                    isHost = true,
                    pingMs = 12.0
                ),
                SyncPlayParticipant(
                    sessionId = "sess-peer",
                    userName = "Remote Peer",
                    isHost = false,
                    pingMs = 38.0
                )
            )
        )

        val roomFlow = MutableStateFlow<SyncPlayRoom?>(room)
        val connectedFlow = MutableStateFlow(true)
        val participantsFlow = MutableStateFlow(room.participants)
        val isHostFlow = MutableStateFlow(true)
        val sessionFlow = MutableStateFlow<String?>("sess-me")

        every { vm.syncPlayRoom } returns roomFlow
        every { vm.syncPlayConnected } returns connectedFlow
        every { vm.syncPlayParticipants } returns participantsFlow
        every { vm.isSyncPlayHost } returns isHostFlow
        every { vm.syncPlayClient.sessionId } returns sessionFlow

        every { vm.transferSyncPlayHost(any()) } just Runs
        every { vm.leaveSyncPlayRoom() } just Runs

        composeTestRule.setContent {
            HDHROpenTheme {
                SyncPlayBottomSheet(
                    playerViewModel = vm,
                    onDismiss = { dismissed = true }
                )
            }
        }

        // Room code display
        composeTestRule.onNodeWithText("ROOM CODE").assertExists()
        composeTestRule.onNodeWithText("PARTY1").assertExists()
        composeTestRule.onNodeWithText("Playing: Super Bowl LIX").assertExists()

        // Copy button
        composeTestRule.onNodeWithText("Copy").performClick()
        composeTestRule.onNodeWithText("Copied!").assertExists()

        // Participants list
        composeTestRule.onNodeWithText("Participants (2)").assertExists()
        composeTestRule.onNodeWithText("Android User (You)").assertExists()
        composeTestRule.onNodeWithText("HOST").assertExists()
        composeTestRule.onNodeWithText("Remote Peer").assertExists()
        composeTestRule.onNodeWithText("38 ms").assertExists()

        // Make Host button for peer
        composeTestRule.onNodeWithText("Make Host").performClick()
        verify { vm.transferSyncPlayHost("sess-peer") }

        // Leave Watch Party button
        composeTestRule.onNodeWithText("Leave Watch Party").performClick()
        verify { vm.leaveSyncPlayRoom() }
        assertTrue(dismissed)
    }
}
