import type { QualityPreference } from './quality-preference';

// The tiers "auto" mode can resolve to - a superset of the manually
// selectable ones (QualityPreference), with "minimal" as a floor below
// "low" that's never offered in the picker (see QUALITY_TIERS in
// backend/app/transcoding.py) but that auto-downgrade can still reach on
// a connection too slow even for "low".
export type AutoTier = 'high' | 'medium' | 'low' | 'minimal';

export interface QualityAdjustment {
	direction: 'down' | 'up';
	tier: AutoTier;
	reason: 'stalling' | 'throughput' | 'recovered';
	at: number;
}

// Ascending order - lowest tier first. "minimal" is the floor auto mode
// can reach on its own (see AutoTier/QUALITY_TIERS in
// backend/app/transcoding.py); it's never offered in the manual picker.
const TIER_ORDER: AutoTier[] = ['minimal', 'low', 'medium', 'high'];
// Rescale target for each tier - mirrors QUALITY_TIERS' scale_height
// column in backend/app/transcoding.py. Used to keep auto-downgrade from
// ever stepping into a tier that would *upscale* past the source's native
// resolution (pure quality loss, not a bandwidth saving) - see
// effectiveAutoTierOrder below.
const TIER_SCALE_HEIGHT: Record<AutoTier, number | null> = {
	high: null,
	medium: 720,
	low: 480,
	minimal: 360,
};
// Target bitrate each tier asks the backend for - mirrors
// QUALITY_TIERS/DEFAULT_MAX_BITRATE_MBPS in backend/app/transcoding.py.
// Used only as a relative yardstick against measured throughput, not
// synced with a per-deployment max_bitrate_mbps override: if an admin has
// lowered that ceiling, the real encode is at or below these numbers
// anyway, so comparing against them just makes auto-downgrade trigger
// a little earlier - erring toward stability, which is the goal.
const TIER_TARGET_MBPS: Record<AutoTier, number> = {
	high: 5.0,
	medium: 3.0,
	low: 1.5,
	minimal: 0.7,
};

// Auto quality adjustment while on "auto": a fast reactive path (repeated
// `waiting` events - recordStallAndMaybeDowngrade below) and a slower
// proactive path (measured throughput vs. the active tier's target
// bitrate - sampleThroughput below, polled from attachPlayer). Stalls
// react to a stutter that already happened; throughput sampling catches
// a degrading connection before the buffer actually empties. Downgrades
// are intentionally quick to trigger (favor smooth playback over
// resolution); upgrades require a longer clean window to avoid flapping
// back and forth at the margin.
const STALL_WINDOW_MS = 20_000;
const STALL_THRESHOLD = 2;
// Throughput sampled every 5s. 3 consecutive low samples (~15s) trigger a
// downgrade; 12 consecutive healthy samples (~60s) with no stalls in that
// window trigger an upgrade.
const DOWNGRADE_SAMPLE_COUNT = 3;
const UPGRADE_SAMPLE_COUNT = 12;
// Downgrade once measured speed drops within 20% of the current tier's
// target (i.e. there's barely any headroom left); require 50% headroom
// above the *next tier up's* target, sustained, before upgrading to it.
const DOWNGRADE_MARGIN = 1.2;
const UPGRADE_MARGIN = 1.5;
// Longer-window steady-state baseline for the CURRENT tier (naturally
// tier-scoped since speedSamplesMbps resets on every tier change - see
// resetSamples()'s call sites). Lets sampleThroughput tell "this stream's
// throughput genuinely dropped" apart from "this stream never needed much
// bitrate in the first place" (e.g. a simple/low-resolution source whose
// real encode sits well under TIER_TARGET_MBPS regardless of network
// speed - the bug this is fixing).
const BASELINE_SAMPLE_COUNT = 24; // ~2 min @ 5s
const BASELINE_DROP_RATIO = 0.5; // recent avg < 50% of this tier's own baseline = genuine drop
// Only trust the absolute TIER_TARGET_MBPS comparison once the baseline
// has actually run close to that target - otherwise a naturally
// low-bitrate stream looks like a perpetual shortfall against a number
// it was never trying to hit, and gets downgraded regardless of the
// network's real condition.
const BASELINE_NEAR_TARGET_RATIO = 0.8;
// Measured throughput alone is not a reliable "the network is struggling"
// signal: for a live, real-time-paced stream, bytes arrive at roughly the
// content's own encode rate (ffmpeg only ever has as many bytes to send as
// it has already encoded), which for perfectly ordinary OTA/cable content
// often sits well under a tier's assumed target even on an abundant-
// bandwidth LAN. The only direct, content-agnostic evidence that playback
// is actually losing ground to real time is the buffer ahead of the
// playhead shrinking over time - a stable or growing buffer proves the
// network is keeping up regardless of what the raw byte-rate looks like.
// So a throughput-based downgrade additionally requires this to be true;
// it's the fix for auto-downgrade firing on fine, fast connections.
const BUFFER_TREND_SAMPLE_COUNT = 4; // ~20s @ 5s - short so a real drain is still caught quickly
const BUFFER_SAFE_FLOOR_SECONDS = 10; // a buffer this large or bigger is never "draining", whatever its trend
const BUFFER_DRAIN_DROP_SECONDS = 3; // net drop required across the window to count as a genuine drain

// The subset of TIER_ORDER that's actually meaningful for a stream of the
// given source height: a tier whose scale_height is >= the source height
// would rescale to the same or a larger frame than the source already is
// (an upscale, or a no-op resize), so it's collapsed out rather than
// offered as a distinct, worse downgrade step. `sourceHeight` null/<=0
// (ffprobe not loaded yet, or failed) falls back to the full unfiltered
// order - the old, resolution-unaware behavior.
function effectiveAutoTierOrder(sourceHeight: number | null): AutoTier[] {
	if (!sourceHeight || sourceHeight <= 0) return TIER_ORDER;
	const ladder = TIER_ORDER.filter(
		(tier) => tier === 'high' || TIER_SCALE_HEIGHT[tier]! < sourceHeight,
	);
	// Keep a floor below "high" even for a sub-360p source, so a
	// connection too slow even for "low" still has a lever to pull -
	// despite "minimal" being technically an upscale there, this is the
	// one deliberate exception to the no-upscale rule above.
	if (ladder.length === 1) ladder.unshift('minimal');
	return ladder;
}

// Walk TIER_ORDER (not the ladder's own positions) so a tier the ladder
// has since collapsed out from under us (e.g. videoInfo resolving after a
// downgrade already landed on it) still has a well-defined next-more- or
// next-less-aggressive neighbor.
function stepDown(tier: AutoTier, ladder: AutoTier[]): AutoTier | null {
	for (let i = TIER_ORDER.indexOf(tier) - 1; i >= 0; i--) {
		if (ladder.includes(TIER_ORDER[i])) return TIER_ORDER[i];
	}
	return null;
}
function stepUp(tier: AutoTier, ladder: AutoTier[]): AutoTier | null {
	for (let i = TIER_ORDER.indexOf(tier) + 1; i < TIER_ORDER.length; i++) {
		if (ladder.includes(TIER_ORDER[i])) return TIER_ORDER[i];
	}
	return null;
}

// The best (highest-quality) tier that a given sustained throughput
// reading can plausibly support, at DOWNGRADE_MARGIN headroom. Lets a
// severely degraded connection (well below even "low") jump straight to
// "minimal" in one step instead of crawling down one tier per ~15s
// sampling window while it keeps stalling along the way.
function bestTierForSpeed(avgMbps: number, ladder: AutoTier[]): AutoTier {
	let best: AutoTier = ladder[0];
	for (const tier of ladder) {
		if (avgMbps >= TIER_TARGET_MBPS[tier] * DOWNGRADE_MARGIN) best = tier;
	}
	return best;
}

// Resolves the tier a stream URL should actually request from the
// backend: the manually-selected tier, or (while on "auto") whatever
// auto-adjustment currently has it pegged at.
export function resolveEffectiveTier(
	quality: QualityPreference,
	autoEffectiveTier: AutoTier,
): QualityPreference | AutoTier {
	return quality === 'auto' ? autoEffectiveTier : quality;
}

// Seconds between the playhead and the end of whatever buffered range
// currently contains it - 0 if the playhead isn't inside any buffered
// range at all (e.g. right after a seek/reload, before the first segment
// lands). Wrapped defensively since `buffered` can throw in some embed/
// test environments; falling back to a large sentinel means "unknown"
// never gets misread as "draining".
function getBufferedAheadSeconds(video: HTMLVideoElement): number {
	try {
		const t = video.currentTime;
		const ranges = video.buffered;
		for (let i = 0; i < ranges.length; i++) {
			if (t >= ranges.start(i) && t <= ranges.end(i)) return ranges.end(i) - t;
		}
		return 0;
	} catch {
		return Number.POSITIVE_INFINITY;
	}
}

export interface QualityControllerOptions {
	getQuality: () => QualityPreference;
	getAutoEffectiveTier: () => AutoTier;
	setAutoEffectiveTier: (tier: AutoTier) => void;
	getSourceHeight: () => number | null;
	getVideoElement: () => HTMLVideoElement | null;
	getThroughputSpeedKBs: () => number | undefined;
	setMeasuredSpeedMbps: (value: number | null) => void;
	setLastQualityAdjustment: (value: QualityAdjustment | null) => void;
	reloadAtCurrentQuality: () => void;
	showPlaybackNotice: (message: string) => void;
	translate: (key: string, options?: { default?: string }) => string;
}

// Owns the "auto" quality ladder's decision logic (and its private
// stall/throughput/buffer sample history) - all of it only ever consulted
// while quality is "auto"; a manual tier choice is never overridden. The
// reactive state it reads or writes (autoEffectiveTier, measuredSpeedMbps,
// lastQualityAdjustment) lives in the owning component and is threaded
// through via the getter/setter options above, same as the other player
// controllers.
export function createQualityController(options: QualityControllerOptions) {
	// Rolling window of recent stalls, used to auto-downgrade quality on a
	// struggling network - see recordStallAndMaybeDowngrade() below.
	let stallTimestamps: number[] = [];
	// Recent measured download-speed samples (Mbps), used for the proactive
	// half of auto quality adjustment - see sampleThroughput(). Most recent
	// last; trimmed to BASELINE_SAMPLE_COUNT.
	let speedSamplesMbps: number[] = [];
	// Recent buffered-ahead samples (seconds between the playhead and the end
	// of the buffered range), sampled alongside speedSamplesMbps. This is the
	// actual "is the network keeping up with real time" ground truth -
	// measured throughput alone can't tell a network-constrained stream apart
	// from a live source that simply doesn't need much bitrate (its bytes
	// arrive at the encoder's real-time pace either way) - see
	// isBufferDraining() for how it gates a downgrade.
	let bufferedAheadSamples: number[] = [];

	// True only once there's a full trend window AND the buffer is both
	// small and has genuinely shrunk across it - a brief wobble in an
	// otherwise large buffer isn't evidence of anything. This is the actual
	// gate on a throughput-based downgrade (see sampleThroughput) - measured
	// byte-rate alone only decides *which* tier to land on once this is true.
	function isBufferDraining(): boolean {
		if (bufferedAheadSamples.length < BUFFER_TREND_SAMPLE_COUNT) return false;
		const oldest = bufferedAheadSamples[0];
		const newest = bufferedAheadSamples[bufferedAheadSamples.length - 1];
		return newest < BUFFER_SAFE_FLOOR_SECONDS && oldest - newest >= BUFFER_DRAIN_DROP_SECONDS;
	}

	// Clears the stall/speed sample history - called whenever the active
	// tier changes for a reason other than the auto-adjustment logic itself
	// (manual quality change, media switch, or a silent auto-tier
	// correction), so stale samples from a previous tier never factor into
	// the next decision. Deliberately leaves bufferedAheadSamples alone -
	// matches the pre-extraction behavior at each of those call sites.
	function resetSamples() {
		stallTimestamps = [];
		speedSamplesMbps = [];
	}

	function applyAutoDowngrade(reason: 'stalling' | 'throughput', target?: AutoTier) {
		const next = target ?? stepDown(options.getAutoEffectiveTier(), effectiveAutoTierOrder(options.getSourceHeight()));
		if (!next) return;
		stallTimestamps = [];
		speedSamplesMbps = [];
		bufferedAheadSamples = [];
		options.setAutoEffectiveTier(next);
		options.setLastQualityAdjustment({ direction: 'down', tier: next, reason, at: Date.now() });
		options.reloadAtCurrentQuality();
		options.showPlaybackNotice(
			options.translate('player.quality_auto_downgraded', {
				default: 'Reduced quality due to network conditions',
			}),
		);
	}

	function recordStallAndMaybeDowngrade() {
		if (options.getQuality() !== 'auto') return;
		const now = Date.now();
		stallTimestamps = [...stallTimestamps.filter((t) => now - t < STALL_WINDOW_MS), now];
		if (stallTimestamps.length < STALL_THRESHOLD) return;
		applyAutoDowngrade('stalling');
	}

	// Polled from attachPlayer while quality is "auto". Reads mpegts.js's
	// live loader speed (KB/s) and reacts to sustained highs/lows rather than
	// single samples, since speed naturally spikes/dips segment-to-segment.
	function sampleThroughput() {
		if (options.getQuality() !== 'auto') return;
		const videoElement = options.getVideoElement();
		if (videoElement) {
			bufferedAheadSamples = [...bufferedAheadSamples, getBufferedAheadSeconds(videoElement)].slice(
				-BUFFER_TREND_SAMPLE_COUNT,
			);
		}
		const speedKBs = options.getThroughputSpeedKBs();
		if (typeof speedKBs !== 'number' || !Number.isFinite(speedKBs) || speedKBs <= 0) return;
		const speedMbps = (speedKBs * 8) / 1000;
		options.setMeasuredSpeedMbps(speedMbps);
		speedSamplesMbps = [...speedSamplesMbps, speedMbps].slice(-BASELINE_SAMPLE_COUNT);

		const autoEffectiveTier = options.getAutoEffectiveTier();
		const ladder = effectiveAutoTierOrder(options.getSourceHeight());
		const avgOf = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

		const recentWindow = speedSamplesMbps.slice(-DOWNGRADE_SAMPLE_COUNT);
		if (recentWindow.length >= DOWNGRADE_SAMPLE_COUNT) {
			const recentAvg = avgOf(recentWindow);
			const baselineAvg = avgOf(speedSamplesMbps);
			const tierTarget = TIER_TARGET_MBPS[autoEffectiveTier];
			const baselineNearTarget = baselineAvg >= tierTarget * BASELINE_NEAR_TARGET_RATIO;

			// Throughput looking low is necessary but not sufficient - it's
			// also what a perfectly healthy LAN reads as for ordinary content,
			// since live bytes arrive at the encoder's pace either way. Only
			// act on it once the buffer itself shows real, sustained drain.
			if (isBufferDraining()) {
				if (baselineNearTarget) {
					// This stream has genuinely been running near its tier's target
					// bitrate, so a shortfall against that target is a trustworthy
					// signal - keep today's behavior, including the multi-step jump
					// for a severely degraded connection.
					if (recentAvg < tierTarget * DOWNGRADE_MARGIN) {
						const target = bestTierForSpeed(recentAvg, ladder);
						if (ladder.indexOf(target) < ladder.indexOf(autoEffectiveTier)) {
							applyAutoDowngrade('throughput', target);
							return;
						}
					}
				} else if (recentAvg < baselineAvg * BASELINE_DROP_RATIO) {
					// The baseline never got near the target in the first place
					// (e.g. a low-resolution/low-complexity source that simply
					// doesn't need much bitrate) - the absolute target means
					// nothing here, so fall back to a relative drop from this
					// stream's own baseline, and only step down one tier since
					// there's no absolute anchor to justify a bigger jump.
					const target = stepDown(autoEffectiveTier, ladder);
					if (target) {
						applyAutoDowngrade('throughput', target);
						return;
					}
				}
			}
		}

		const nextUp = stepUp(autoEffectiveTier, ladder);
		if (!nextUp) return;
		const upgradeWindow = speedSamplesMbps.slice(-UPGRADE_SAMPLE_COUNT);
		if (upgradeWindow.length < UPGRADE_SAMPLE_COUNT) return;
		if (stallTimestamps.length > 0) return;
		const avgAll = avgOf(upgradeWindow);
		if (avgAll < TIER_TARGET_MBPS[nextUp] * UPGRADE_MARGIN) return;
		speedSamplesMbps = [];
		options.setAutoEffectiveTier(nextUp);
		options.setLastQualityAdjustment({ direction: 'up', tier: nextUp, reason: 'recovered', at: Date.now() });
		options.reloadAtCurrentQuality();
		options.showPlaybackNotice(
			options.translate('player.quality_auto_upgraded', { default: 'Network improved - increasing quality' }),
		);
	}

	// Corrects autoEffectiveTier if videoInfo's source height resolves or
	// changes (e.g. an in-progress recording's ffprobe data lagging behind a
	// stall-driven downgrade) *after* auto mode already landed on a tier the
	// now-known resolution collapses out of effectiveAutoTierOrder - e.g. a
	// downgrade to "medium" (720p rescale) that turns out to upscale a 480p
	// source once its real height is known. Silent on purpose (no toast/
	// lastQualityAdjustment update) since this isn't a network event - purely
	// an internal correction. Self-limiting: the landing tier is always
	// ladder-valid, so it no-ops on the next run.
	function correctAutoTierForSourceHeight() {
		if (options.getQuality() !== 'auto') return;
		const autoEffectiveTier = options.getAutoEffectiveTier();
		const ladder = effectiveAutoTierOrder(options.getSourceHeight());
		if (ladder.includes(autoEffectiveTier)) return;
		let corrected: AutoTier = 'high';
		for (let i = TIER_ORDER.indexOf(autoEffectiveTier) + 1; i < TIER_ORDER.length; i++) {
			if (ladder.includes(TIER_ORDER[i])) {
				corrected = TIER_ORDER[i];
				break;
			}
		}
		options.setAutoEffectiveTier(corrected);
		resetSamples();
		options.reloadAtCurrentQuality();
	}

	return {
		resetSamples,
		recordStallAndMaybeDowngrade,
		sampleThroughput,
		correctAutoTierForSourceHeight,
	};
}
