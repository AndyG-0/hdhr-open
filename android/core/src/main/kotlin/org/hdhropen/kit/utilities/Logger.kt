package org.hdhropen.kit.utilities

import android.util.Log as AndroidLog

class TaggedLogger(private val tag: String) {
    fun debug(message: String) {
        AndroidLog.d(tag, message)
    }

    fun info(message: String) {
        AndroidLog.i(tag, message)
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
