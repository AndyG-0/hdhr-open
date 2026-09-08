package org.hdhropen.kit

import io.mockk.*
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runTest
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.APIError
import org.hdhropen.kit.networking.WatchSessionManager
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class WatchSessionManagerTest {

    private lateinit var apiClient: APIClient
    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)
    private lateinit var manager: WatchSessionManager

    @Before
    fun setUp() {
        apiClient = mockk(relaxed = true)
        manager = WatchSessionManager(apiClient, testScope)
    }

    @After
    fun tearDown() {
        manager.stopWatch()
    }

    @Test
    fun testInitialState() {
        assertNull(manager.activeSessionId.value)
        assertNull(manager.activeRecordingId.value)
        assertFalse(manager.isPromoted.value)
    }

    @Test
    fun testStartWatch_success() = testScope.runTest {
        val recording = HDHomeRunRecording(
            recordingId = "rec-123",
            sessionId = "sess-456",
            title = "Live Channel"
        )
        coEvery { apiClient.startWatch("5.1") } returns recording

        val result = manager.startWatch("5.1")
        assertEquals(recording, result)
        assertEquals("sess-456", manager.activeSessionId.value)
        assertEquals("rec-123", manager.activeRecordingId.value)
        assertFalse(manager.isPromoted.value)

        manager.stopWatch()
    }

    @Test
    fun testStartWatch_nullResponse() = testScope.runTest {
        coEvery { apiClient.startWatch("5.1") } returns null

        val result = manager.startWatch("5.1")
        assertNull(result)
        assertNull(manager.activeSessionId.value)
        assertNull(manager.activeRecordingId.value)
    }

    @Test
    fun testPromoteWatch_success() = testScope.runTest {
        val recording = HDHomeRunRecording(
            recordingId = "rec-123",
            sessionId = "sess-456",
            title = "Live Channel"
        )
        coEvery { apiClient.startWatch("5.1") } returns recording
        coEvery { apiClient.promoteWatch("sess-456", any()) } returns recording

        manager.startWatch("5.1")
        val promoted = manager.promoteWatch(null)

        assertEquals(recording, promoted)
        assertTrue(manager.isPromoted.value)

        // Stopping a promoted watch should NOT call stopWatch on API
        manager.stopWatch()
        coVerify(exactly = 0) { apiClient.stopWatch("sess-456") }
    }

    @Test
    fun testPromoteWatch_noActiveSession_throws() = testScope.runTest {
        try {
            manager.promoteWatch(null)
            fail("Expected NoActiveWatchSession exception")
        } catch (e: APIError.NoActiveWatchSession) {
            // Expected
        }
    }

    @Test
    fun testStopWatch_activeSession_callsApi() = testScope.runTest {
        val recording = HDHomeRunRecording(
            recordingId = "rec-123",
            sessionId = "sess-456",
            title = "Live Channel"
        )
        coEvery { apiClient.startWatch("5.1") } returns recording

        manager.startWatch("5.1")
        manager.stopWatch()
        testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { apiClient.stopWatch("sess-456") }
        assertNull(manager.activeSessionId.value)
        assertNull(manager.activeRecordingId.value)
        assertFalse(manager.isPromoted.value)
    }
}
