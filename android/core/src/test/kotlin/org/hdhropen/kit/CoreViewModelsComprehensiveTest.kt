package org.hdhropen.kit

import io.mockk.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.AuthManager
import org.hdhropen.kit.viewmodels.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class CoreViewModelsComprehensiveTest {

    private val testDispatcher = StandardTestDispatcher()
    private lateinit var apiClient: APIClient
    private lateinit var authManager: AuthManager

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        apiClient = mockk(relaxed = true)
        authManager = mockk(relaxed = true)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    // MARK: - GuideViewModel Tests

    @Test
    fun testGuideViewModel_displayedChannelsAndFavorites() = runTest {
        val vm = GuideViewModel(apiClient)
        val ch1 = HDHomeRunChannel(channelNumber = "2.1", name = "CBS")
        val ch2 = HDHomeRunChannel(channelNumber = "4.1", name = "NBC")

        coEvery { apiClient.getChannels() } returns HDHomeRunChannelsResponse(channels = listOf(ch1, ch2), guideAvailable = true)
        coEvery { apiClient.getNetworkIntegration("hdhomerun") } returns NetworkIntegration(
            id = "hdhr",
            type = "hdhomerun",
            name = "HDHomeRun",
            settings = mapOf("favorite_channels" to JsonArray(listOf(JsonPrimitive("2.1"))))
        )

        vm.loadData()
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(2, vm.channels.value.size)
        assertTrue(vm.guideAvailable.value)
        assertEquals(setOf("2.1"), vm.favoriteChannels.value)

        // All channels displayed when filter is false
        assertEquals(2, vm.displayedChannels.size)

        // Only favorites displayed when filter is true
        vm.filterOnlyFavorites.value = true
        assertEquals(1, vm.displayedChannels.size)
        assertEquals("2.1", vm.displayedChannels[0].channelNumber)

        // Toggle favorite
        vm.toggleFavorite("4.1")
        testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.favoriteChannels.value.contains("4.1"))

        vm.toggleFavorite("2.1")
        testDispatcher.scheduler.advanceUntilIdle()
        assertFalse(vm.favoriteChannels.value.contains("2.1"))
    }

    @Test
    fun testGuideViewModel_rulesAndAirings() = runTest {
        val vm = GuideViewModel(apiClient)
        val rule = HDHomeRunRecordingRule(recordingRuleId = "r1", seriesId = "s1", title = "News")
        coEvery { apiClient.addRecordingRule(any()) } returns listOf(rule)
        coEvery { apiClient.updateRecordingRule(any(), any()) } returns listOf(rule)
        coEvery { apiClient.deleteRecordingRule(any()) } returns emptyList()
        coEvery { apiClient.listRecordingRules() } returns listOf(rule)

        vm.recordEpisode(seriesId = "s1", channelNumber = "2.1", start = 1000.0)
        testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.recordingRules.value.size)

        vm.recordSeries(seriesId = "s1", channelNumber = "2.1")
        testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.recordingRules.value.size)

        vm.updateRule(ruleId = "r1", isSeries = true)
        testDispatcher.scheduler.advanceUntilIdle()

        vm.cancelRule("r1")
        testDispatcher.scheduler.advanceUntilIdle()

        // getAirings
        val nowEntry = HDHomeRunGuideEntry(title = "Morning Show", start = 100.0, end = 200.0)
        val nextEntry = HDHomeRunGuideEntry(title = "Noon News", start = 200.0, end = 300.0)
        val channel = HDHomeRunChannel(channelNumber = "5.1", name = "FOX", now = nowEntry, next = nextEntry)

        coEvery { apiClient.getChannels() } returns HDHomeRunChannelsResponse(channels = listOf(channel))
        vm.loadChannels()
        val airings = vm.getAirings("5.1")
        assertEquals(2, airings.size)
        assertEquals("Morning Show", airings[0].title)

        val emptyAirings = vm.getAirings("99.9")
        assertTrue(emptyAirings.isEmpty())
    }

    // MARK: - RecordingsViewModel Tests

    @Test
    fun testRecordingsViewModel_filteringAndMutations() = runTest {
        val vm = RecordingsViewModel(apiClient)
        val showRec = HDHomeRunRecording(title = "Sitcom", recordingId = "r1", categoryType = "shows", seasonNumber = 1)
        val movieRec = HDHomeRunRecording(title = "Blockbuster", recordingId = "r2", category = "Movie")
        val sportRec = HDHomeRunRecording(title = "Football", recordingId = "r3", category = "Sports")
        val inProgRec = HDHomeRunRecording(title = "Live Game", recordingId = "r4", recordEnd = System.currentTimeMillis() / 1000.0 + 3600)

        val all = listOf(showRec, movieRec, sportRec, inProgRec)
        coEvery { apiClient.listRecordings() } returns all
        coEvery { apiClient.getDvrInfo() } returns HDHomeRunDvrInfo(freeSpaceBytes = 1000L)

        vm.loadData()
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(4, vm.recordings.value.size)
        assertEquals(4, vm.filteredRecordings.size)

        // SHOWS
        vm.selectedFilter.value = RecordingCategoryFilter.SHOWS
        assertEquals(1, vm.filteredRecordings.size)
        assertEquals("Sitcom", vm.filteredRecordings[0].title)

        // MOVIES
        vm.selectedFilter.value = RecordingCategoryFilter.MOVIES
        assertEquals(1, vm.filteredRecordings.size)
        assertEquals("Blockbuster", vm.filteredRecordings[0].title)

        // SPORTS
        vm.selectedFilter.value = RecordingCategoryFilter.SPORTS
        assertEquals(1, vm.filteredRecordings.size)
        assertEquals("Football", vm.filteredRecordings[0].title)

        // IN_PROGRESS
        vm.selectedFilter.value = RecordingCategoryFilter.IN_PROGRESS
        assertEquals(1, vm.filteredRecordings.size)
        assertEquals("Live Game", vm.filteredRecordings[0].title)

        // Delete recording
        vm.deleteRecording(showRec)
        testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(3, vm.recordings.value.size)

        // Create keyword rule
        vm.createKeywordRule("Mystery", RecordingRuleOptions(keywordQuery = "Sherlock"))
        testDispatcher.scheduler.advanceUntilIdle()
        coVerify { apiClient.addRecordingRule(any()) }
    }

    // MARK: - TunerViewModel Tests

    @Test
    fun testTunerViewModel_loadingAndPolling() = runTest {
        val vm = TunerViewModel(apiClient)
        val tuner = HDHomeRunTuner(index = 0, resource = "tuner0")
        val info = HDHomeRunTunerInfo(friendlyName = "HDHR Connect")

        coEvery { apiClient.getTunerStatus() } returns listOf(tuner)
        coEvery { apiClient.getTunerInfo() } returns info

        vm.loadData()
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(1, vm.tuners.value.size)
        assertEquals("HDHR Connect", vm.tunerInfo.value?.friendlyName)
        assertFalse(vm.isLoading.value)

        // Polling
        vm.startPolling(100)
        testScheduler.advanceTimeBy(250)
        coVerify(atLeast = 2) { apiClient.getTunerStatus() }
        vm.stopPolling()
    }

    // MARK: - SettingsViewModel Tests

    @Test
    fun testSettingsViewModel_loadData() = runTest {
        val vm = SettingsViewModel(apiClient)
        val settings = AppSettings(timezone = "America/New_York")
        val presets = listOf(HDHomeRunTranscodePreset(id = "p1", label = "720p", description = "HD"))

        coEvery { apiClient.getSettings() } returns settings
        coEvery { apiClient.getTranscodePresets() } returns presets
        coEvery { apiClient.getHWAccelDiagnostics() } returns HWAccelDiagnostics(device = "vaapi")

        vm.loadData()
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("America/New_York", vm.settings.value?.timezone)
        assertEquals(1, vm.transcodePresets.value.size)
        assertEquals("vaapi", vm.hwAccelDiagnostics.value?.device)
        assertFalse(vm.isLoading.value)
    }

    // MARK: - AuthViewModel Tests

    @Test
    fun testAuthViewModel_profileSelectionAndPin() = runTest {
        val vm = AuthViewModel(authManager)
        val profileWithPin = UserProfile(id = "u1", name = "Mom", hasPin = true)
        val profileWithoutPin = UserProfile(id = "u2", name = "Kids", hasPin = false)

        // Unprotected profile logs in immediately
        vm.selectProfile(profileWithoutPin)
        testDispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 1) { authManager.login(profileWithoutPin, null) }
        assertFalse(vm.showPinEntry.value)

        // Protected profile requires PIN
        vm.selectProfile(profileWithPin)
        assertTrue(vm.showPinEntry.value)
        assertEquals("", vm.pin.value)

        // Digits
        vm.appendPinDigit("1")
        vm.appendPinDigit("2")
        assertEquals("12", vm.pin.value)

        vm.deletePinDigit()
        assertEquals("1", vm.pin.value)

        vm.appendPinDigit("3")
        vm.appendPinDigit("4")
        vm.appendPinDigit("5") // 4th digit -> triggers login
        testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { authManager.login(profileWithPin, "1345") }
        assertFalse(vm.showPinEntry.value)

        // Dismiss
        vm.selectProfile(profileWithPin)
        vm.dismissPinEntry()
        assertFalse(vm.showPinEntry.value)
        assertNull(vm.selectedProfile.value)
    }

    // MARK: - PlayerViewModel Tests

    @Test
    fun testPlayerViewModel_audioSelectionAndPlaybackControls() = runTest {
        val watchSessionManager = mockk<org.hdhropen.kit.networking.WatchSessionManager>(relaxed = true)
        val playerEngine = org.hdhropen.kit.playback.PlayerEngine()
        val captionController = org.hdhropen.kit.playback.CaptionController()
        val vm = PlayerViewModel(apiClient, watchSessionManager, playerEngine, captionController)

        val track1 = HDHomeRunRecordingAudioInfo(index = 0, title = "Main", channels = 2)
        val track2 = HDHomeRunRecordingAudioInfo(index = 1, title = "Spanish", channels = 2)
        playerEngine.setAudioTracks(listOf(track1, track2), selectedTrack = track1)

        val rec = HDHomeRunRecording(
            recordingId = "rec_99",
            title = "Movie Night",
            playUrl = "/api/dvr/rec_99.mpg",
            provider = "internal"
        )

        coEvery { apiClient.baseURL } returns "http://127.0.0.1:8000"
        coEvery { apiClient.createRecordingHLSSession(any(), any(), any(), any(), any(), any()) } returns
            org.hdhropen.kit.networking.HLSSessionResponse(
                sessionId = "rec_sess_hls",
                playlistUrl = "/api/hls/rec_sess_hls/playlist.m3u8"
            )

        vm.playRecording(rec)
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("rec_sess_hls", vm.activeHLSSessionId.value)
        assertEquals("Movie Night", vm.activeRecording.value?.title)

        // Select second audio track
        vm.selectAudioTrack(track2)
        testDispatcher.scheduler.advanceUntilIdle()

        coVerify {
            apiClient.createRecordingHLSSession(
                url = "/api/dvr/rec_99.mpg",
                recordingId = "rec_99",
                start = any(),
                audioIndex = 1,
                provider = "internal",
                forCast = any()
            )
        }
        assertEquals(track2, playerEngine.currentAudioTrack.value)

        // Playback controls
        vm.play()
        vm.pause()
        vm.togglePlayPause()
        vm.seek(20.0)
        vm.skipForward(15.0)
        vm.skipBackward(10.0)
        vm.retry()
        testDispatcher.scheduler.advanceUntilIdle()
        assertNotNull(vm.activeRecording.value)

        // SyncPlay controls
        vm.createSyncPlayRoom("Alice")
        vm.joinSyncPlayRoom("ROOM1", "Bob")
        vm.transferSyncPlayHost("target_sess")
        vm.leaveSyncPlayRoom()
        testDispatcher.scheduler.advanceUntilIdle()
    }

    @Test
    fun testPlayerViewModel_channelAndPromote() = runTest {
        val watchSessionManager = mockk<org.hdhropen.kit.networking.WatchSessionManager>(relaxed = true)
        val playerEngine = org.hdhropen.kit.playback.PlayerEngine()
        val captionController = org.hdhropen.kit.playback.CaptionController()
        val vm = PlayerViewModel(apiClient, watchSessionManager, playerEngine, captionController)

        val channel = HDHomeRunChannel(channelNumber = "5.1", name = "KING")
        val watchRec = HDHomeRunRecording(recordingId = "rec_live_51", title = "KING Live", playUrl = "/api/dvr/live_51.mpg")

        coEvery { apiClient.baseURL } returns "http://127.0.0.1:8000"
        coEvery { watchSessionManager.startWatch("5.1") } returns watchRec
        coEvery { apiClient.createRecordingHLSSession(any(), any(), any(), any(), any(), any()) } returns
            org.hdhropen.kit.networking.HLSSessionResponse(
                sessionId = "sess_watch_hls",
                playlistUrl = "/api/hls/sess_watch_hls/playlist.m3u8"
            )
        coEvery { watchSessionManager.promoteWatch() } returns watchRec.copy(title = "Promoted KING Live")

        vm.playChannel(channel)
        testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.isWatchSession.value)
        assertEquals("KING", vm.activeChannel.value?.name)

        vm.promoteToRecording()
        testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.isPromoted.value)
        assertEquals("Promoted KING Live", vm.activeRecording.value?.title)

        vm.closePlayer()
        assertNull(vm.activeChannel.value)
    }
}
