package org.hdhropen.kit

import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.AuthManager
import org.hdhropen.kit.networking.InMemoryCookieJar
import org.hdhropen.kit.networking.ServerDiscovery
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.hdhropen.kit.viewmodels.RecordingCategoryFilter
import org.hdhropen.kit.viewmodels.RecordingsViewModel
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.*
import org.junit.Test

class ViewModelsTest {
    @Test
    fun testRecordingsFiltering() {
        val client = APIClient("http://localhost:8000")
        val vm = RecordingsViewModel(client)

        val rec1 = HDHomeRunRecording(
            recordingId = "1",
            title = "Daily Show",
            seasonNumber = 1,
            episodeNumber = "1",
            categoryType = "shows"
        )
        val rec2 = HDHomeRunRecording(
            recordingId = "2",
            title = "The Matrix",
            category = "Movie",
            categoryType = "movies"
        )
        val rec3 = HDHomeRunRecording(
            recordingId = "3",
            title = "NFL Football",
            category = "Sports",
            categoryType = "sports"
        )

        // Reflection or test load
        val field = RecordingsViewModel::class.java.getDeclaredField("_recordings")
        field.isAccessible = true
        @Suppress("UNCHECKED_CAST")
        val stateFlow = field.get(vm) as kotlinx.coroutines.flow.MutableStateFlow<List<HDHomeRunRecording>>
        stateFlow.value = listOf(rec1, rec2, rec3)

        vm.selectedFilter.value = RecordingCategoryFilter.ALL
        assertEquals(3, vm.filteredRecordings.size)

        vm.selectedFilter.value = RecordingCategoryFilter.SHOWS
        assertEquals(1, vm.filteredRecordings.size)
        assertEquals("Daily Show", vm.filteredRecordings[0].title)

        vm.selectedFilter.value = RecordingCategoryFilter.MOVIES
        assertEquals(1, vm.filteredRecordings.size)
        assertEquals("The Matrix", vm.filteredRecordings[0].title)

        vm.selectedFilter.value = RecordingCategoryFilter.SPORTS
        assertEquals(1, vm.filteredRecordings.size)
        assertEquals("NFL Football", vm.filteredRecordings[0].title)
    }

    @Test
    fun testGuideAiringsRetrieval() {
        val client = APIClient("http://localhost:8000")
        val vm = GuideViewModel(client)

        val airing1 = HDHomeRunGuideEntry(title = "Morning News", start = 100.0, end = 200.0)
        val full = HDHomeRunFullGuideChannel(
            channelNumber = "5.1",
            channelName = "KING",
            airings = listOf(airing1)
        )

        val field = GuideViewModel::class.java.getDeclaredField("_fullGuide")
        field.isAccessible = true
        @Suppress("UNCHECKED_CAST")
        val stateFlow = field.get(vm) as kotlinx.coroutines.flow.MutableStateFlow<List<HDHomeRunFullGuideChannel>>
        stateFlow.value = listOf(full)

        val airings = vm.getAirings("5.1")
        assertEquals(1, airings.size)
        assertEquals("Morning News", airings[0].title)
    }

    @Test
    fun testServerDiscoveryURLUpdate() {
        val discovery = ServerDiscovery(null, "http://127.0.0.1:8000")
        assertEquals("http://127.0.0.1:8000", discovery.serverURLString.value)

        val client = APIClient(discovery.serverURLString.value)
        assertEquals("http://127.0.0.1:8000", client.baseURL)

        val newUrl = "http://192.168.1.100:8000"
        discovery.setServerURL(newUrl)
        client.baseURL = newUrl

        assertEquals(newUrl, discovery.serverURLString.value)
        assertEquals(newUrl, client.baseURL)
    }

    @Test
    fun testAuthManagerInitialState() {
        val client = APIClient("http://127.0.0.1:8000")
        val authManager = AuthManager(client, null)

        assertNull(authManager.currentUser.value)
        assertFalse(authManager.isAuthenticated)
        assertTrue(authManager.profiles.value.isEmpty())
        assertFalse(authManager.isLoading.value)
        assertNull(authManager.authError.value)
    }

    @Test
    fun testInMemoryCookieJar() {
        val jar = InMemoryCookieJar()
        val url = "http://127.0.0.1:8000/api/devices/register".toHttpUrl()
        val cookie = okhttp3.Cookie.Builder()
            .name("hdhropen_device")
            .value("device-abc-123")
            .domain("127.0.0.1")
            .path("/")
            .build()

        jar.saveFromResponse(url, listOf(cookie))
        val loaded = jar.loadForRequest(url)
        assertEquals(1, loaded.size)
        val firstCookie = loaded.first()
        assertEquals("hdhropen_device", firstCookie.name)
        assertEquals("device-abc-123", firstCookie.value)

        jar.clear()
        val empty = jar.loadForRequest(url)
        assertEquals(0, empty.size)
    }

    @Test
    fun testAPIClientDeviceIdField() {
        val client = APIClient("http://127.0.0.1:8000")
        assertNull(client.deviceId)
        client.deviceId = "dev-test-123"
        assertEquals("dev-test-123", client.deviceId)
    }
}
