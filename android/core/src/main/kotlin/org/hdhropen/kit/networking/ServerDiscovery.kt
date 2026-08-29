package org.hdhropen.kit.networking

import android.content.Context
import android.content.SharedPreferences
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.hdhropen.kit.utilities.Log
import java.net.InetAddress
import java.util.concurrent.TimeUnit

data class DiscoveredServer(
    val name: String,
    val url: String,
    val isReachable: Boolean = true
) {
    val id: String get() = url
}

class ServerDiscovery(
    private val context: Context? = null,
    defaultURL: String = "http://127.0.0.1:8000"
) {
    private val serverURLStorageKey = "org.hdhropen.client.serverURL"
    private val prefsName = "hdhr_open_server_prefs"

    private val prefs: SharedPreferences? by lazy {
        context?.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
    }

    private val _discoveredServers = MutableStateFlow<List<DiscoveredServer>>(emptyList())
    val discoveredServers: StateFlow<List<DiscoveredServer>> = _discoveredServers.asStateFlow()

    private val _isSearching = MutableStateFlow(false)
    val isSearching: StateFlow<Boolean> = _isSearching.asStateFlow()

    private val _serverURLString = MutableStateFlow(
        prefs?.getString(serverURLStorageKey, null) ?: defaultURL
    )
    val serverURLString: StateFlow<String> = _serverURLString.asStateFlow()

    private var nsdManager: NsdManager? = null
    private var discoveryListener: NsdManager.DiscoveryListener? = null
    private val serviceType = "_http._tcp."

    private val testClient = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.SECONDS)
        .build()

    fun setServerURL(url: String) {
        _serverURLString.value = url
        prefs?.edit()?.putString(serverURLStorageKey, url)?.apply()
    }

    fun startDiscovery() {
        if (_isSearching.value) return
        _isSearching.value = true
        _discoveredServers.value = emptyList()

        if (context == null) return
        nsdManager = context.getSystemService(Context.NSD_SERVICE) as? NsdManager

        discoveryListener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(regType: String) {
                Log.network.info("NSD discovery started: $regType")
            }

            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                val serviceName = serviceInfo.serviceName.lowercase()
                if (serviceName.contains("hdhr") || serviceName.contains("homerun")) {
                    resolveService(serviceInfo)
                }
            }

            override fun onServiceLost(serviceInfo: NsdServiceInfo) {
                Log.network.debug("NSD service lost: ${serviceInfo.serviceName}")
            }

            override fun onDiscoveryStopped(serviceType: String) {
                Log.network.info("NSD discovery stopped")
                _isSearching.value = false
            }

            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.network.error("NSD start discovery failed: $errorCode")
                stopDiscovery()
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) {
                Log.network.error("NSD stop discovery failed: $errorCode")
                _isSearching.value = false
            }
        }

        try {
            nsdManager?.discoverServices(serviceType, NsdManager.PROTOCOL_DNS_SD, discoveryListener)
        } catch (e: Exception) {
            Log.network.error("Failed to start NSD: ${e.localizedMessage}")
            _isSearching.value = false
        }
    }

    private fun resolveService(serviceInfo: NsdServiceInfo) {
        nsdManager?.resolveService(serviceInfo, object : NsdManager.ResolveListener {
            override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                Log.network.warning("NSD resolve failed: $errorCode")
            }

            override fun onServiceResolved(serviceInfo: NsdServiceInfo) {
                val host: InetAddress = serviceInfo.host ?: return
                val port = serviceInfo.port
                val hostAddress = host.hostAddress ?: return
                val url = "http://$hostAddress:$port"

                val server = DiscoveredServer(
                    name = serviceInfo.serviceName,
                    url = url
                )

                val current = _discoveredServers.value.toMutableList()
                if (current.none { it.id == server.id }) {
                    current.add(server)
                    _discoveredServers.value = current
                }
            }
        })
    }

    fun stopDiscovery() {
        try {
            discoveryListener?.let { nsdManager?.stopServiceDiscovery(it) }
        } catch (e: Exception) {
            // Ignore if already stopped
        }
        discoveryListener = null
        nsdManager = null
        _isSearching.value = false
    }

    suspend fun testConnection(url: String): Boolean = withContext(Dispatchers.IO) {
        val checkUrl = "${url.trimEnd('/')}/api/setup/status"
        try {
            val req = Request.Builder().url(checkUrl).get().build()
            val resp = testClient.newCall(req).execute()
            resp.isSuccessful
        } catch (e: Exception) {
            false
        }
    }
}
