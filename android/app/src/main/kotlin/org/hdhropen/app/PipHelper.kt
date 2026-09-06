package org.hdhropen.app

import android.app.PendingIntent
import android.app.RemoteAction
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon
import android.util.Rational

object PipHelper {
    const val ACTION_PIP_PLAY = "org.hdhropen.app.PIP_PLAY"
    const val ACTION_PIP_PAUSE = "org.hdhropen.app.PIP_PAUSE"
    const val ACTION_PIP_REWIND = "org.hdhropen.app.PIP_REWIND"
    const val ACTION_PIP_FORWARD = "org.hdhropen.app.PIP_FORWARD"

    const val REQUEST_CODE_PLAY = 101
    const val REQUEST_CODE_PAUSE = 102
    const val REQUEST_CODE_REWIND = 103
    const val REQUEST_CODE_FORWARD = 104

    /**
     * Computes the Picture-in-Picture aspect ratio safely clamped to the
     * range mandated by Android OS: [1:2.39, 2.39:1] (approx. 0.41841 to 2.39).
     * Ratios outside this range would cause Android's PictureInPictureParams.Builder
     * to throw an IllegalArgumentException.
     */
    fun calculateAspectRatio(videoWidth: Int?, videoHeight: Int?): Rational {
        if (videoWidth != null && videoHeight != null && videoWidth > 0 && videoHeight > 0) {
            val ratio = videoWidth.toFloat() / videoHeight.toFloat()
            return when {
                ratio < 0.41841f -> Rational(100, 239)
                ratio > 2.39f -> Rational(239, 100)
                else -> Rational(videoWidth, videoHeight)
            }
        }
        return Rational(16, 9)
    }

    /**
     * Builds the list of RemoteActions for the PiP overlay:
     * - Rewind 10s (if content is seekable)
     * - Play / Pause toggle
     * - Forward 10s (if content is seekable)
     */
    fun buildRemoteActions(
        context: Context,
        isPlaying: Boolean,
        isSeekable: Boolean
    ): List<RemoteAction> {
        val actions = mutableListOf<RemoteAction>()

        if (isSeekable) {
            val rewindIntent = PendingIntent.getBroadcast(
                context,
                REQUEST_CODE_REWIND,
                Intent(ACTION_PIP_REWIND).setPackage(context.packageName),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            actions.add(
                RemoteAction(
                    Icon.createWithResource(context, R.drawable.ic_pip_replay_10),
                    context.getString(R.string.pip_rewind),
                    context.getString(R.string.pip_rewind_desc),
                    rewindIntent
                )
            )
        }

        val (action, iconRes, titleRes, reqCode) = if (isPlaying) {
            Quad(ACTION_PIP_PAUSE, R.drawable.ic_pip_pause, R.string.pip_pause, REQUEST_CODE_PAUSE)
        } else {
            Quad(ACTION_PIP_PLAY, R.drawable.ic_pip_play, R.string.pip_play, REQUEST_CODE_PLAY)
        }

        val playPauseIntent = PendingIntent.getBroadcast(
            context,
            reqCode,
            Intent(action).setPackage(context.packageName),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        actions.add(
            RemoteAction(
                Icon.createWithResource(context, iconRes),
                context.getString(titleRes),
                context.getString(titleRes),
                playPauseIntent
            )
        )

        if (isSeekable) {
            val forwardIntent = PendingIntent.getBroadcast(
                context,
                REQUEST_CODE_FORWARD,
                Intent(ACTION_PIP_FORWARD).setPackage(context.packageName),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            actions.add(
                RemoteAction(
                    Icon.createWithResource(context, R.drawable.ic_pip_forward_10),
                    context.getString(R.string.pip_forward),
                    context.getString(R.string.pip_forward_desc),
                    forwardIntent
                )
            )
        }

        return actions
    }

    private data class Quad<A, B, C, D>(val first: A, val second: B, val third: C, val fourth: D)
}
