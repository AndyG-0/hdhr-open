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
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.DiscoveryBucketFilter
import org.hdhropen.kit.viewmodels.DiscoveryViewModel
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

@OptIn(ExperimentalCoroutinesApi::class)
class DiscoveryViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)
    private lateinit var server: MockWebServer
    private lateinit var apiClient: APIClient
    private lateinit var viewModel: DiscoveryViewModel
    // A plain scope sharing the test dispatcher - not testScope.backgroundScope, whose
    // tasks aren't reliably pumped by advanceUntilIdle() - backing the ViewModel's
    // filteredItems stateIn collector; cancelled manually in tearDown() since nothing
    // else owns its lifetime.
    private lateinit var viewModelScope: CoroutineScope

    private val discoveryBody = """
        {
            "has_profile": true,
            "enabled": true,
            "items": [
                {"title": "Personalized Drama", "bucket": "shows", "source": "personalized"},
                {"title": "Oscar Marathon", "bucket": "movies", "source": "network_pick"},
                {"title": "Lakers at Celtics", "bucket": "sports", "source": "favorite_team"}
            ]
        }
    """.trimIndent()

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        server = MockWebServer()
        server.start()
        val url = server.url("/").toString().removeSuffix("/")
        apiClient = APIClient(baseURL = url, ioDispatcher = testDispatcher)
        viewModelScope = CoroutineScope(testDispatcher + Job())
        viewModel = DiscoveryViewModel(apiClient, externalScope = viewModelScope)
    }

    @After
    fun tearDown() {
        viewModelScope.cancel()
        server.shutdown()
        Dispatchers.resetMain()
    }

    @Test
    fun testFilteredItemsDefaultsToAllItemsUnfiltered() = testScope.runTest {
        server.enqueue(MockResponse().setResponseCode(200).setBody(discoveryBody))

        viewModel.loadData()
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(3, viewModel.items.value.size)
        assertEquals(3, viewModel.filteredItems.value.size)
    }

    @Test
    fun testSettingFilterNarrowsFilteredItemsToThatBucket() = testScope.runTest {
        server.enqueue(MockResponse().setResponseCode(200).setBody(discoveryBody))

        viewModel.loadData()
        testDispatcher.scheduler.advanceUntilIdle()

        viewModel.setFilter(DiscoveryBucketFilter.SPORTS)
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(1, viewModel.filteredItems.value.size)
        assertEquals("Lakers at Celtics", viewModel.filteredItems.value[0].title)
    }

    @Test
    fun testSwitchingFilterDoesNotIssueANewNetworkRequest() = testScope.runTest {
        server.enqueue(MockResponse().setResponseCode(200).setBody(discoveryBody))

        viewModel.loadData()
        testDispatcher.scheduler.advanceUntilIdle()
        server.takeRequest(5, TimeUnit.SECONDS)

        viewModel.setFilter(DiscoveryBucketFilter.MOVIES)
        testDispatcher.scheduler.advanceUntilIdle()

        assertNull(server.takeRequest(0, TimeUnit.MILLISECONDS))
    }

    @Test
    fun testSwitchingBackToAllRestoresEveryItem() = testScope.runTest {
        server.enqueue(MockResponse().setResponseCode(200).setBody(discoveryBody))

        viewModel.loadData()
        testDispatcher.scheduler.advanceUntilIdle()

        viewModel.setFilter(DiscoveryBucketFilter.SHOWS)
        testDispatcher.scheduler.advanceUntilIdle()
        viewModel.setFilter(DiscoveryBucketFilter.ALL)
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(3, viewModel.filteredItems.value.size)
    }
}
