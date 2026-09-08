package org.hdhropen.app

import android.content.Intent
import android.graphics.Rect
import androidx.media3.common.util.UnstableApi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@UnstableApi
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class MainActivityPipTest {

    @Test
    fun testPipActionConstants() {
        assertEquals("org.hdhropen.app.PIP_PLAY", PipHelper.ACTION_PIP_PLAY)
        assertEquals("org.hdhropen.app.PIP_PAUSE", PipHelper.ACTION_PIP_PAUSE)
        assertEquals("org.hdhropen.app.PIP_REWIND", PipHelper.ACTION_PIP_REWIND)
        assertEquals("org.hdhropen.app.PIP_FORWARD", PipHelper.ACTION_PIP_FORWARD)
    }

    @Test
    fun testMainActivityLifecycleAndPipSetup() {
        val controller = Robolectric.buildActivity(MainActivity::class.java)
        controller.create().start().resume()
        val activity = controller.get()

        assertNotNull(activity)
        assertEquals(false, activity.isInPipMode.value)

        // Test video bounds update
        val testBounds = Rect(0, 0, 1920, 1080)
        activity.updateVideoBounds(testBounds)

        val params = activity.buildPipParams()
        assertNotNull(params)

        // Destroy
        controller.pause().stop().destroy()
    }

    @Test
    fun testPipBroadcastReceiverHandling() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).create().start().resume()
        val context = RuntimeEnvironment.getApplication()

        // Send PiP broadcast intents
        val playIntent = Intent(PipHelper.ACTION_PIP_PLAY).setPackage(context.packageName)
        context.sendBroadcast(playIntent)

        val pauseIntent = Intent(PipHelper.ACTION_PIP_PAUSE).setPackage(context.packageName)
        context.sendBroadcast(pauseIntent)

        val rewindIntent = Intent(PipHelper.ACTION_PIP_REWIND).setPackage(context.packageName)
        context.sendBroadcast(rewindIntent)

        val forwardIntent = Intent(PipHelper.ACTION_PIP_FORWARD).setPackage(context.packageName)
        context.sendBroadcast(forwardIntent)

        controller.pause().stop().destroy()
    }
}
