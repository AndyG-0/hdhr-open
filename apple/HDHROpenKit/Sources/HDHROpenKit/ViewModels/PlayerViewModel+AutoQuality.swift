import Foundation

/// The full internal auto-quality ladder, including `.minimal` - a rung the
/// manual `VideoQuality` picker never offers directly but the auto poll can
/// still step down to. Mirrors Android's `AutoTier`/`AUTO_TIER_ORDER` and the
/// web player's `TIER_TARGET_MBPS` ladder; values must stay numerically
/// identical across all three clients. Declared without `private` (like
/// `PlayerViewModel.lastRawCues` et al.) so `@testable import` test code can
/// seed `PlayerViewModel.autoEffectiveTier` and drive `sampleAutoQualityTick()`
/// directly, mirroring Android's `PlayerViewModelQualityTest`.
enum AutoTier: Sendable {
    case minimal
    case low
    case medium
    case high

    var backendValue: String {
        switch self {
        case .minimal: "minimal"
        case .low: "low"
        case .medium: "medium"
        case .high: "high"
        }
    }

    var targetMbps: Double {
        switch self {
        case .minimal: 0.7
        case .low: 1.5
        case .medium: 3.0
        case .high: 5.0
        }
    }

    var maxSourceHeight: Int? {
        switch self {
        case .minimal: 360
        case .low: 480
        case .medium: 720
        case .high: nil
        }
    }
}

private let autoTierOrder: [AutoTier] = [.minimal, .low, .medium, .high]

extension VideoQuality {
    /// The auto-tier a manual selection corresponds to - `.auto` itself maps
    /// to `.high` since that's where the auto poll always starts a fresh
    /// session before it has any samples to judge. Not `private`:
    /// PlayerViewModel.swift uses this from a separate file in the same
    /// module.
    var autoTier: AutoTier {
        switch self {
        case .low: .low
        case .medium: .medium
        case .high, .auto: .high
        }
    }
}

/// Trims the ladder to tiers that would actually look different for a given
/// source resolution - mirrors Android's `effectiveAutoTierOrder`/web's
/// `effectiveTierOrder`. A source already at or below a tier's cap wouldn't
/// visibly upscale by landing on it, so those tiers collapse into `.minimal`.
private func effectiveAutoTierOrder(sourceHeight: Int?) -> [AutoTier] {
    guard let sourceHeight, sourceHeight > 0 else { return autoTierOrder }
    let ladder = autoTierOrder.filter { tier in
        guard let cap = tier.maxSourceHeight else { return true }
        return cap < sourceHeight
    }
    return ladder.isEmpty ? [.minimal] : ladder
}

private func stepDown(_ tier: AutoTier, ladder: [AutoTier]) -> AutoTier? {
    guard let idx = autoTierOrder.firstIndex(of: tier) else { return nil }
    for i in stride(from: idx - 1, through: 0, by: -1) where ladder.contains(autoTierOrder[i]) {
        return autoTierOrder[i]
    }
    return nil
}

private func stepUp(_ tier: AutoTier, ladder: [AutoTier]) -> AutoTier? {
    guard let idx = autoTierOrder.firstIndex(of: tier) else { return nil }
    for i in (idx + 1)..<autoTierOrder.count where ladder.contains(autoTierOrder[i]) {
        return autoTierOrder[i]
    }
    return nil
}

/// Picks the highest tier in `ladder` whose target is still within reach of
/// `avgMbps` (after the downgrade margin), for landing on a tier once a
/// downgrade has already been justified by a stall or buffer-drain signal -
/// never the trigger for a downgrade itself. Mirrors Android's/web's
/// `bestTierForSpeed`.
private func bestTierForSpeed(_ avgMbps: Double, ladder: [AutoTier], downgradeMargin: Double) -> AutoTier {
    var best = ladder.first ?? .minimal
    for tier in ladder where avgMbps >= tier.targetMbps * downgradeMargin {
        best = tier
    }
    return best
}

/// Auto-quality polling/sampling, split out of `PlayerViewModel.swift` to
/// keep that file under SwiftLint's file-length cap. `autoQualityPollTask`,
/// `autoEffectiveTier`, `stallTimestamps`, `speedSamplesMbps`, and
/// `bufferedAheadSamples` remain stored properties on `PlayerViewModel`
/// itself (extensions can't add stored instance properties); `switchToQuality`
/// also remains there (shared with the manual quality picker).
extension PlayerViewModel {
    // Auto-quality constants (CC-12 parity fix) - must stay numerically
    // identical to HDHomeRunPlayer.svelte and Android's PlayerViewModel.kt.
    private static let throughputSampleIntervalNanos: UInt64 = 5_000_000_000
    private static let downgradeSampleCount = 3
    private static let upgradeSampleCount = 12
    private static let downgradeMargin = 1.2
    private static let upgradeMargin = 1.5
    private static let baselineSampleCount = 24
    private static let baselineDropRatio = 0.5
    private static let baselineNearTargetRatio = 0.8
    private static let bufferTrendSampleCount = 4
    private static let bufferSafeFloorSeconds = 10.0
    private static let bufferDrainDropSeconds = 3.0

    /// Starts the auto-quality poll if the just-negotiated session actually
    /// succeeded (an `activeHLSSessionId` was set) and the user's preference
    /// is AUTO. Called after `sessionCoordinator.startChannel`/`startRecording`
    /// returns, success or failure alike.
    func maybeStartAutoQualityPolling() {
        guard quality == .auto, activeHLSSessionId != nil else { return }
        startAutoQualityPolling()
    }

    func startAutoQualityPolling() {
        guard playbackMode == .serverTranscodedHls else { return }
        guard autoQualityPollTask == nil else { return }
        resetAutoQualitySamples()
        autoQualityPollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: Self.throughputSampleIntervalNanos)
                guard let self, quality == .auto else { break }
                await sampleAutoQualityTick()
            }
        }
    }

    func stopAutoQualityPolling() {
        autoQualityPollTask?.cancel()
        autoQualityPollTask = nil
    }

    func resetAutoQualitySamples() {
        speedSamplesMbps.removeAll()
        bufferedAheadSamples.removeAll()
        stallTimestamps.removeAll()
    }

    /// True only once a full window of buffered-ahead samples is collected
    /// AND the newest sample is below the safety floor AND it has shrunk by
    /// at least `bufferDrainDropSeconds` since the oldest sample in the
    /// window - a one-off wobble in an otherwise-healthy buffer is not a
    /// signal. Mirrors Android's `isBufferDraining()`/web's `isBufferDraining()`.
    private func isBufferDraining() -> Bool {
        guard bufferedAheadSamples.count >= Self.bufferTrendSampleCount,
              let newest = bufferedAheadSamples.last,
              let oldest = bufferedAheadSamples.first
        else { return false }
        return newest < Self.bufferSafeFloorSeconds && (oldest - newest) >= Self.bufferDrainDropSeconds
    }

    /// The core auto-quality gate, polled every 5s while `quality == .auto`.
    /// Buffer-drain is the necessary gate for any throughput-triggered
    /// downgrade - measured speed alone only picks *which* tier to land on
    /// once a stall or buffer-drain has already justified a downgrade.
    /// Mirrors Android's `sampleAutoQualityTick()`/web's `sampleThroughput()`.
    func sampleAutoQualityTick() async {
        if let bufferedAhead = playerEngine.bufferedAheadSeconds() {
            bufferedAheadSamples.append(bufferedAhead)
            while bufferedAheadSamples.count > Self.bufferTrendSampleCount {
                bufferedAheadSamples.removeFirst()
            }
        }

        guard let observedBitrate = playerEngine.observedBitrate else { return }
        let speedMbps = observedBitrate / 1_000_000.0
        speedSamplesMbps.append(speedMbps)
        while speedSamplesMbps.count > Self.baselineSampleCount {
            speedSamplesMbps.removeFirst()
        }

        let ladder = effectiveAutoTierOrder(sourceHeight: playerEngine.videoSpecs?.height)
        let tier = autoEffectiveTier

        let recentWindow = speedSamplesMbps.suffix(Self.downgradeSampleCount)
        if recentWindow.count >= Self.downgradeSampleCount, isBufferDraining() {
            let recentAvg = recentWindow.reduce(0, +) / Double(recentWindow.count)
            let baselineAvg = speedSamplesMbps.reduce(0, +) / Double(speedSamplesMbps.count)
            let baselineNearTarget = baselineAvg >= tier.targetMbps * Self.baselineNearTargetRatio

            if baselineNearTarget {
                if recentAvg < tier.targetMbps * Self.downgradeMargin {
                    let target = bestTierForSpeed(recentAvg, ladder: ladder, downgradeMargin: Self.downgradeMargin)
                    if let targetIdx = autoTierOrder.firstIndex(of: target),
                       let tierIdx = autoTierOrder.firstIndex(of: tier),
                       targetIdx < tierIdx
                    {
                        await applyAutoAdjustment(target)
                        return
                    }
                }
            } else if recentAvg < baselineAvg * Self.baselineDropRatio {
                if let target = stepDown(tier, ladder: ladder) {
                    await applyAutoAdjustment(target)
                    return
                }
            }
        }

        guard let nextUp = stepUp(tier, ladder: ladder) else { return }
        let upgradeWindow = speedSamplesMbps.suffix(Self.upgradeSampleCount)
        guard upgradeWindow.count >= Self.upgradeSampleCount, stallTimestamps.isEmpty else { return }
        let upgradeAvg = upgradeWindow.reduce(0, +) / Double(upgradeWindow.count)
        guard upgradeAvg >= nextUp.targetMbps * Self.upgradeMargin else { return }
        await applyAutoAdjustment(nextUp)
    }

    /// Fires a single one-tier downgrade from the reactive stall path, which
    /// runs synchronously from a Combine sink - spawns its own `Task` to
    /// reach the async `switchToQuality`, mirroring Android's
    /// `applyAutoDowngradeOneTier()` (launched fire-and-forget there too).
    func applyAutoDowngradeOneTier() {
        let ladder = effectiveAutoTierOrder(sourceHeight: playerEngine.videoSpecs?.height)
        guard let target = stepDown(autoEffectiveTier, ladder: ladder) else { return }
        Task { [weak self] in
            await self?.applyAutoAdjustment(target)
        }
    }

    private func applyAutoAdjustment(_ target: AutoTier) async {
        autoEffectiveTier = target
        resetAutoQualitySamples()
        await switchToQuality(target.backendValue)
    }
}
