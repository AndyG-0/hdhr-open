package org.hdhropen.kit

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.RecordingsViewModel
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

@OptIn(ExperimentalCoroutinesApi::class)
class RecordingsViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private lateinit var server: MockWebServer
    private lateinit var apiClient: APIClient
    private lateinit var viewModel: RecordingsViewModel
    // A plain scope sharing the test dispatcher - not testScope.backgroundScope, whose
    // tasks aren't reliably pumped by advanceUntilIdle() - backing the ViewModel's debounce
    // collector; cancelled manually in tearDown() since nothing else owns its lifetime.
    private lateinit var viewModelScope: CoroutineScope

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        server = MockWebServer()
        server.start()
        val url = server.url("/").toString().removeSuffix("/")
        apiClient = APIClient(baseURL = url, ioDispatcher = testDispatcher)
        viewModelScope = CoroutineScope(testDispatcher + Job())
        viewModel = RecordingsViewModel(apiClient, externalScope = viewModelScope)
    }

    @After
    fun tearDown() {
        viewModelScope.cancel()
        server.shutdown()
        Dispatchers.resetMain()
    }

    private fun enqueueRecordings(vararg titles: String) {
        val recordings = titles.map { HDHomeRunRecording(title = it, recordingId = it) }
        server.enqueue(MockResponse().setResponseCode(200).setBody(json.encodeToString(recordings)))
    }

    // Starts the debounce collector and runs it to the point where it's actively waiting
    // on searchQuery's next change - so the test's own mutations are the collector's first
    // observed values, rather than racing its own startup.
    private fun TestScope.startSearchObserver() {
        viewModel.startSearchObserver()
        testDispatcher.scheduler.runCurrent()
    }

    @Test
    fun testTypingDoesNotFetchBeforeDebounceWindowElapses() = testScope.runTest {
        startSearchObserver()
        enqueueRecordings("Matched Show")

        viewModel.searchQuery.value = "match"
        testDispatcher.scheduler.advanceTimeBy(100)
        testDispatcher.scheduler.runCurrent()

        assertNull(server.takeRequest(0, TimeUnit.MILLISECONDS))
    }

    @Test
    fun testDebouncedSearchRefetchesWithSearchParam() = testScope.runTest {
        startSearchObserver()
        enqueueRecordings("Matched Show")

        viewModel.searchQuery.value = "match"
        testDispatcher.scheduler.advanceUntilIdle()

        val recorded = server.takeRequest(5, TimeUnit.SECONDS)
        assertNotNull(recorded)
        assertTrue(recorded!!.path!!.contains("search=match"))
        assertEquals(1, viewModel.recordings.value.size)
        assertEquals("Matched Show", viewModel.recordings.value[0].title)
    }

    @Test
    fun testRapidTypingOnlyFetchesTheLatestQuery() = testScope.runTest {
        startSearchObserver()
        enqueueRecordings("First Result")
        enqueueRecordings("Second Result")

        viewModel.searchQuery.value = "fir"
        testDispatcher.scheduler.advanceTimeBy(100)
        testDispatcher.scheduler.runCurrent()
        viewModel.searchQuery.value = "firs"
        testDispatcher.scheduler.advanceTimeBy(100)
        testDispatcher.scheduler.runCurrent()
        viewModel.searchQuery.value = "first"
        testDispatcher.scheduler.advanceUntilIdle()

        // Only the settled, final query should have produced a request - collectLatest
        // cancels the in-flight load for each superseded intermediate value.
        val recorded = server.takeRequest(5, TimeUnit.SECONDS)
        assertNotNull(recorded)
        assertTrue(recorded!!.path!!.contains("search=first"))
        assertNull(server.takeRequest(0, TimeUnit.MILLISECONDS))
    }

    @Test
    fun testClearingSearchRefetchesWithoutSearchParam() = testScope.runTest {
        startSearchObserver()
        enqueueRecordings("Matched Show")
        viewModel.searchQuery.value = "match"
        testDispatcher.scheduler.advanceUntilIdle()
        server.takeRequest(5, TimeUnit.SECONDS)

        enqueueRecordings("Everything")
        viewModel.searchQuery.value = ""
        testDispatcher.scheduler.advanceUntilIdle()

        val recorded = server.takeRequest(5, TimeUnit.SECONDS)
        assertNotNull(recorded)
        assertFalse(recorded!!.path!!.contains("search="))
    }

    @Test
    fun testLoadRecordingsDefaultsToTheActiveSearchTerm() = testScope.runTest {
        enqueueRecordings("Matched Show")
        viewModel.searchQuery.value = "match"
        testDispatcher.scheduler.advanceUntilIdle()
        server.takeRequest(5, TimeUnit.SECONDS)

        // A manual refresh (e.g. the screen's Refresh button, which calls loadRecordings()
        // with no explicit argument) should re-issue the currently active search term.
        enqueueRecordings("Matched Show")
        viewModel.loadRecordings()
        testDispatcher.scheduler.advanceUntilIdle()

        val recorded = server.takeRequest(5, TimeUnit.SECONDS)
        assertNotNull(recorded)
        assertTrue(recorded!!.path!!.contains("search=match"))
    }
}
