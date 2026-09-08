package org.hdhropen.app

import android.content.Context
import com.google.android.gms.cast.CastMediaControlIntent
import org.hdhropen.app.cast.CastOptionsProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class CastOptionsProviderTest {

    private val context: Context
        get() = RuntimeEnvironment.getApplication()

    @Test
    fun testCastOptionsConfiguredWithDefaultReceiverAppId() {
        val provider = CastOptionsProvider()
        val options = provider.getCastOptions(context)
        assertNotNull(options)
        assertEquals(CastMediaControlIntent.DEFAULT_MEDIA_RECEIVER_APPLICATION_ID, options.receiverApplicationId)
    }

    @Test
    fun testAdditionalSessionProvidersIsNull() {
        val provider = CastOptionsProvider()
        assertNull(provider.getAdditionalSessionProviders(context))
    }
}
