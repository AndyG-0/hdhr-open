package org.hdhropen.kit

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.hdhropen.kit.networking.DiscoveredServer
import org.hdhropen.kit.networking.ServerDiscovery
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class ServerDiscoveryTest {

    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun testDiscoveredServerModel() {
        val discovered = DiscoveredServer(name = "HDHomeRun DVR", url = "http://192.168.1.100:8000")
        assertEquals("http://192.168.1.100:8000", discovered.id)
        assertEquals("HDHomeRun DVR", discovered.name)
        assertTrue(discovered.isReachable)
    }

    @Test
    fun testServerDiscovery_urlAndState() {
        val discovery = ServerDiscovery(defaultURL = "http://10.0.0.1:8000")
        assertEquals("http://10.0.0.1:8000", discovery.serverURLString.value)
        assertFalse(discovery.isSearching.value)
        assertTrue(discovery.discoveredServers.value.isEmpty())

        discovery.setServerURL("http://10.0.0.2:8000")
        assertEquals("http://10.0.0.2:8000", discovery.serverURLString.value)

        // startDiscovery with null context
        discovery.startDiscovery()
        assertTrue(discovery.isSearching.value)

        // Calling start again when already searching returns early
        discovery.startDiscovery()
        assertTrue(discovery.isSearching.value)

        discovery.stopDiscovery()
        assertFalse(discovery.isSearching.value)
    }

    @Test
    fun testTestConnection() = runBlocking {
        val discovery = ServerDiscovery()
        val url = server.url("/").toString().removeSuffix("/")

        // Success
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"needs_setup\":false}"))
        val success = discovery.testConnection(url)
        assertTrue(success)

        // Failure response code
        server.enqueue(MockResponse().setResponseCode(500))
        val failure = discovery.testConnection(url)
        assertFalse(failure)

        // Network error (invalid URL)
        val unreachable = discovery.testConnection("http://192.0.2.1:1")
        assertFalse(unreachable)
    }
}
