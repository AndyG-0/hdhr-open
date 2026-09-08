package org.hdhropen.kit

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.hdhropen.kit.models.CurrentUser
import org.hdhropen.kit.models.DeviceRegisterResult
import org.hdhropen.kit.models.UserProfile
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.APIError
import org.hdhropen.kit.networking.AuthManager
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class AuthManagerTest {

    private val testDispatcher = UnconfinedTestDispatcher()
    private lateinit var apiClient: APIClient
    private lateinit var authManager: AuthManager

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        apiClient = mockk(relaxed = true)
        authManager = AuthManager(apiClient, context = null)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun testInitialState() {
        assertNull(authManager.currentUser.value)
        assertFalse(authManager.isAuthenticated)
        assertTrue(authManager.profiles.value.isEmpty())
        assertFalse(authManager.isLoading.value)
        assertNull(authManager.authError.value)
    }

    @Test
    fun testSetCurrentUser() {
        val user = CurrentUser(id = "u1", name = "Test User")
        authManager.setCurrentUser(user)
        assertEquals(user, authManager.currentUser.value)
        assertTrue(authManager.isAuthenticated)

        authManager.setCurrentUser(null)
        assertNull(authManager.currentUser.value)
        assertFalse(authManager.isAuthenticated)
    }

    @Test
    fun testRegisterDeviceSuccess() = runTest {
        coEvery { apiClient.registerDevice() } returns DeviceRegisterResult(id = "dev-123", name = "Test Dev")

        val result = authManager.registerDeviceIfNeeded()
        assertTrue(result)
        coVerify { apiClient.deviceId = "dev-123" }
    }

    @Test
    fun testRegisterDeviceFailure() = runTest {
        coEvery { apiClient.registerDevice() } throws RuntimeException("Network down")

        val result = authManager.registerDeviceIfNeeded()
        assertFalse(result)
    }

    @Test
    fun testFetchProfilesSuccess() = runTest {
        val profileList = listOf(
            UserProfile(id = "p1", name = "Profile 1"),
            UserProfile(id = "p2", name = "Profile 2")
        )
        coEvery { apiClient.listProfiles() } returns profileList

        authManager.fetchProfiles()

        assertEquals(profileList, authManager.profiles.value)
        assertFalse(authManager.isLoading.value)
        assertNull(authManager.authError.value)
    }

    @Test
    fun testFetchProfilesError() = runTest {
        coEvery { apiClient.listProfiles() } throws RuntimeException("Failed to fetch")

        authManager.fetchProfiles()

        assertTrue(authManager.profiles.value.isEmpty())
        assertFalse(authManager.isLoading.value)
        assertEquals("Failed to fetch", authManager.authError.value)
    }

    @Test
    fun testLoginSuccess() = runTest {
        val profile = UserProfile(id = "p1", name = "User 1")
        val loggedIn = CurrentUser(id = "p1", name = "User 1", token = "jwt-token")
        coEvery { apiClient.login(userId = "p1", pin = "1234", tokenName = any()) } returns loggedIn

        authManager.login(profile, "1234")

        assertEquals(loggedIn, authManager.currentUser.value)
        assertTrue(authManager.isAuthenticated)
        coVerify { apiClient.bearerToken = "jwt-token" }
        assertFalse(authManager.isLoading.value)
        assertNull(authManager.authError.value)
    }

    @Test
    fun testLoginUnauthorizedRetryWithDeviceRegistration() = runTest {
        val profile = UserProfile(id = "p1", name = "User 1")
        val loggedIn = CurrentUser(id = "p1", name = "User 1", token = "jwt-retry-token")

        coEvery { apiClient.registerDevice() } returns DeviceRegisterResult(id = "dev-auto", name = "Auto Dev")
        coEvery { apiClient.login(userId = "p1", pin = null, tokenName = any()) } throws
                APIError.Unauthorized("device not registered") andThen loggedIn

        authManager.login(profile, null)

        assertEquals(loggedIn, authManager.currentUser.value)
        coVerify(exactly = 2) { apiClient.login(userId = "p1", pin = null, tokenName = any()) }
    }

    @Test
    fun testLoginUnauthorizedWithoutDeviceKeywordThrows() = runTest {
        val profile = UserProfile(id = "p1", name = "User 1")
        coEvery { apiClient.login(userId = "p1", pin = "wrong", tokenName = any()) } throws
                APIError.Unauthorized("Invalid PIN")

        var caught: Throwable? = null
        try {
            authManager.login(profile, "wrong")
        } catch (e: Throwable) {
            caught = e
        }
        assertTrue(caught is APIError.Unauthorized)
        assertEquals("Invalid PIN", authManager.authError.value)
    }

    @Test
    fun testLogout() = runTest {
        authManager.setCurrentUser(CurrentUser(id = "u1", name = "Test"))
        coEvery { apiClient.logout() } returns Unit

        authManager.logout()

        assertNull(authManager.currentUser.value)
        assertFalse(authManager.isAuthenticated)
        coVerify { apiClient.bearerToken = null }
    }

    @Test
    fun testLogoutHandlesExceptionCleanly() = runTest {
        authManager.setCurrentUser(CurrentUser(id = "u1", name = "Test"))
        coEvery { apiClient.logout() } throws RuntimeException("Network lost")

        authManager.logout()

        assertNull(authManager.currentUser.value)
        assertFalse(authManager.isAuthenticated)
    }

    @Test
    fun testRestoreSessionWithoutPrefsIsNoOp() = runTest {
        coEvery { apiClient.registerDevice() } returns DeviceRegisterResult(id = "dev-1", name = "Dev 1")
        authManager.restoreSession()
        assertNull(authManager.currentUser.value)
    }
}
