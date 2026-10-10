package org.hdhropen.kit.utilities

import android.util.Log as AndroidLog
import org.hdhropen.kit.BuildConfig

class TaggedLogger(private val tag: String) {
    // Verbose/debug-level logs are gated out of release builds - they're
    // developer-oriented noise (and can carry more detail than warning/error
    // messages do), while warning/error stay unconditional in every build so
    // real failures are always visible.
    fun debug(message: String) {
        if (BuildConfig.DEBUG) {
            AndroidLog.d(tag, message)
        }
    }

    fun info(message: String) {
        if (BuildConfig.DEBUG) {
            AndroidLog.i(tag, message)
        }
    }

    fun warning(message: String) {
        AndroidLog.w(tag, message)
    }

    fun error(message: String, throwable: Throwable? = null) {
        if (throwable != null) {
            AndroidLog.e(tag, message, throwable)
        } else {
            AndroidLog.e(tag, message)
        }
    }
}

object Log {
    val general = TaggedLogger("HDHROpen.General")
    val network = TaggedLogger("HDHROpen.Network")
    val player = TaggedLogger("HDHROpen.Player")
    val dvr = TaggedLogger("HDHROpen.DVR")
    val auth = TaggedLogger("HDHROpen.Auth")
}
