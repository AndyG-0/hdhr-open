package org.hdhropen.kit.viewmodels

import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.hdhropen.kit.playback.QualityPreference

// Auto-quality constants (CC-12 parity fix) - must stay numerically
// identical to HDHomeRunPlayer.svelte and Apple's
// PlayerViewModel+AutoQuality.swift.
private const val THROUGHPUT_SAMPLE_INTERVAL_MS = 5_000L
private const val DOWNGRADE_SAMPLE_COUNT = 3
private const val UPGRADE_SAMPLE_COUNT = 12
private const val DOWNGRADE_MARGIN = 1.2
private const val UPGRADE_MARGIN = 1.5
private const val BASELINE_SAMPLE_COUNT = 24
private const val BASELINE_DROP_RATIO = 0.5
private const val BASELINE_NEAR_TARGET_RATIO = 0.8
private const val BUFFER_TREND_SAMPLE_COUNT = 4
private const val BUFFER_SAFE_FLOOR_SECONDS = 10.0
private const val BUFFER_DRAIN_DROP_SECONDS = 3.0

/**
 * Mirrors TIER_ORDER/TIER_TARGET_MBPS/TIER_SCALE_HEIGHT in
 * HDHomeRunPlayer.svelte - the full tier ladder the auto-quality poll can
 * step through, including `minimal`, which the manual QualityPreference
 * picker never offers directly. Not private: PlayerViewModel.kt uses this
 * from a separate file in the same module.
 */
internal enum class AutoTier(val backendValue: String, val targetMbps: Double, val maxSourceHeight: Int?) {
    MINIMAL("minimal", 0.7, 360),
    LOW("low", 1.5, 480),
    MEDIUM("medium", 3.0, 720),
    HIGH("high", 5.0, null)
}

private val AUTO_TIER_ORDER = listOf(AutoTier.MINIMAL, AutoTier.LOW, AutoTier.MEDIUM, AutoTier.HIGH)

/** Not private: PlayerViewModel.kt uses this from a separate file in the same module. */
internal fun QualityPreference.toAutoTier(): AutoTier = when (this) {
    QualityPreference.LOW -> AutoTier.LOW
    QualityPreference.MEDIUM -> AutoTier.MEDIUM
    QualityPreference.HIGH, QualityPreference.AUTO -> AutoTier.HIGH
}

// A tier only belongs on the ladder if upscaling to it would actually mean
// something for this source - same rationale as effectiveAutoTierOrder() in
// HDHomeRunPlayer.svelte. Unknown source resolution keeps the full ladder.
private fun effectiveAutoTierOrder(sourceHeight: Int?): List<AutoTier> {
    if (sourceHeight == null || sourceHeight <= 0) return AUTO_TIER_ORDER
    val ladder = AUTO_TIER_ORDER.filter { it == AutoTier.HIGH || (it.maxSourceHeight ?: Int.MAX_VALUE) < sourceHeight }
    return if (ladder.size == 1) listOf(AutoTier.MINIMAL) + ladder else ladder
}

private fun stepDown(tier: AutoTier, ladder: List<AutoTier>): AutoTier? {
    val idx = AUTO_TIER_ORDER.indexOf(tier)
    for (i in idx - 1 downTo 0) {
        if (AUTO_TIER_ORDER[i] in ladder) return AUTO_TIER_ORDER[i]
    }
    return null
}

private fun stepUp(tier: AutoTier, ladder: List<AutoTier>): AutoTier? {
    val idx = AUTO_TIER_ORDER.indexOf(tier)
    for (i in idx + 1 until AUTO_TIER_ORDER.size) {
        if (AUTO_TIER_ORDER[i] in ladder) return AUTO_TIER_ORDER[i]
    }
    return null
}

private fun bestTierForSpeed(avgMbps: Double, ladder: List<AutoTier>, downgradeMargin: Double): AutoTier {
    var best = ladder.first()
    for (tier in ladder) {
        if (avgMbps >= tier.targetMbps * downgradeMargin) best = tier
    }
    return best
}

// Auto-quality polling/sampling, split out of PlayerViewModel.kt to keep
// that class under detekt's LargeClass cap. `autoEffectiveTier`,
// `autoQualityPollJob`, `stallTimestamps`, `speedSamplesMbps`, and
// `bufferedAheadSamples` remain stored properties on PlayerViewModel
// itself (extension functions can't add stored properties); `switchToQuality`
// also remains there (shared with the manual quality picker).

// Called once a session's loadMedia() has actually been issued - Direct
// play has no HLS session to adjust, so it's never started there.
internal fun PlayerViewModel.maybeStartAutoQualityPolling() {
    if (_quality.value == QualityPreference.AUTO) startAutoQualityPolling()
}

internal fun PlayerViewModel.resetAutoQualitySamples() {
    speedSamplesMbps.clear()
    bufferedAheadSamples.clear()
    stallTimestamps.clear()
}

// Called right after closePlayer() at the start of playChannel()/
// playRecording() (PlayerViewModel+Streaming.kt), before any network call -
// refreshes the per-session quality pick from the persisted default so a
// prior session's manual override doesn't leak into unrelated content. Not
// private: cross-file.
internal fun PlayerViewModel.initializeQualityForNewSession() {
    stopAutoQualityPolling()
    _quality.value = playbackPreferences.qualityPreference.value
    autoEffectiveTier = if (_quality.value == QualityPreference.AUTO) AutoTier.HIGH else _quality.value.toAutoTier()
}

private fun PlayerViewModel.isBufferDraining(): Boolean {
    if (bufferedAheadSamples.size < BUFFER_TREND_SAMPLE_COUNT) return false
    val newest = bufferedAheadSamples.last()
    val oldest = bufferedAheadSamples.first()
    return newest < BUFFER_SAFE_FLOOR_SECONDS && (oldest - newest) >= BUFFER_DRAIN_DROP_SECONDS
}

internal fun PlayerViewModel.startAutoQualityPolling() {
    if (_playbackMode.value == PlaybackMode.Direct) return
    if (autoQualityPollJob?.isActive == true) return
    resetAutoQualitySamples()
    autoQualityPollJob = viewModelScope.launch {
        while (isActive) {
            delay(THROUGHPUT_SAMPLE_INTERVAL_MS)
            if (_quality.value != QualityPreference.AUTO) break
            sampleAutoQualityTick()
        }
    }
}

internal fun PlayerViewModel.stopAutoQualityPolling() {
    autoQualityPollJob?.cancel()
    autoQualityPollJob = null
}

// Mirrors sampleThroughput() in HDHomeRunPlayer.svelte: buffer-drain is
// the necessary gate for any throughput-triggered downgrade: measured
// speed alone only picks *which* tier to land on once (1) or (2) from
// the shared design has already justified a downgrade.
internal fun PlayerViewModel.sampleAutoQualityTick() {
    playerEngine.bufferedAheadSeconds()?.let { bufferedAhead ->
        bufferedAheadSamples.add(bufferedAhead)
        while (bufferedAheadSamples.size > BUFFER_TREND_SAMPLE_COUNT) bufferedAheadSamples.removeAt(0)
    }

    val speedMbps = (playerEngine.observedBitrateBps.value ?: return) / 1_000_000.0
    speedSamplesMbps.add(speedMbps)
    while (speedSamplesMbps.size > BASELINE_SAMPLE_COUNT) speedSamplesMbps.removeAt(0)

    val ladder = effectiveAutoTierOrder(playerEngine.videoSpecs.value?.height)
    val tier = autoEffectiveTier

    val recentWindow = speedSamplesMbps.takeLast(DOWNGRADE_SAMPLE_COUNT)
    if (recentWindow.size >= DOWNGRADE_SAMPLE_COUNT && isBufferDraining()) {
        val recentAvg = recentWindow.average()
        val baselineAvg = speedSamplesMbps.average()
        val tierTarget = tier.targetMbps
        val baselineNearTarget = baselineAvg >= tierTarget * BASELINE_NEAR_TARGET_RATIO

        if (baselineNearTarget) {
            if (recentAvg < tierTarget * DOWNGRADE_MARGIN) {
                val target = bestTierForSpeed(recentAvg, ladder, DOWNGRADE_MARGIN)
                if (AUTO_TIER_ORDER.indexOf(target) < AUTO_TIER_ORDER.indexOf(tier)) {
                    applyAutoAdjustment(target)
                    return
                }
            }
        } else if (recentAvg < baselineAvg * BASELINE_DROP_RATIO) {
            stepDown(tier, ladder)?.let { target ->
                applyAutoAdjustment(target)
                return
            }
        }
    }

    val nextUp = stepUp(tier, ladder) ?: return
    val upgradeWindow = speedSamplesMbps.takeLast(UPGRADE_SAMPLE_COUNT)
    if (upgradeWindow.size < UPGRADE_SAMPLE_COUNT) return
    if (stallTimestamps.isNotEmpty()) return
    if (upgradeWindow.average() < nextUp.targetMbps * UPGRADE_MARGIN) return
    applyAutoAdjustment(nextUp)
}

internal fun PlayerViewModel.applyAutoDowngradeOneTier() {
    val ladder = effectiveAutoTierOrder(playerEngine.videoSpecs.value?.height)
    val target = stepDown(autoEffectiveTier, ladder) ?: return
    applyAutoAdjustment(target)
}

private fun PlayerViewModel.applyAutoAdjustment(target: AutoTier) {
    autoEffectiveTier = target
    resetAutoQualitySamples()
    switchToQuality(target.backendValue)
}
