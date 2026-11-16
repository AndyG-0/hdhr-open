import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { createQualityController, type AutoTier } from './quality-controller';

// Minimal stand-in for an HTMLVideoElement - only currentTime/buffered are read.
function fakeVideo(bufferedAhead: { value: number }) {
	return {
		currentTime: 100,
		get buffered() {
			return {
				length: 1,
				start: () => 100,
				end: () => 100 + bufferedAhead.value,
			};
		},
	} as unknown as HTMLVideoElement;
}

function setup() {
	let tier: AutoTier = 'high';
	const bufferedAhead = { value: 20 };
	const speedKBs = { value: 2000 }; // 16 Mbps - plenty for "high"
	const video = fakeVideo(bufferedAhead);
	const reloadAtCurrentQuality = vi.fn();
	const setMeasuredSpeedMbps = vi.fn();
	const controller = createQualityController({
		getQuality: () => 'auto',
		getAutoEffectiveTier: () => tier,
		setAutoEffectiveTier: (t) => {
			tier = t;
		},
		getSourceHeight: () => 1080,
		getVideoElement: () => video,
		getThroughputSpeedKBs: () => speedKBs.value,
		setMeasuredSpeedMbps,
		setLastQualityAdjustment: vi.fn(),
		reloadAtCurrentQuality,
		showPlaybackNotice: vi.fn(),
		translate: (key) => key,
	});
	return { controller, getTier: () => tier, bufferedAhead, speedKBs, reloadAtCurrentQuality, setMeasuredSpeedMbps };
}

describe('quality-controller restart grace', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(1_000_000);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('still downgrades on two real stalls within the window (regression)', () => {
		const { controller, getTier } = setup();
		controller.recordStallAndMaybeDowngrade();
		vi.advanceTimersByTime(5_000);
		controller.recordStallAndMaybeDowngrade();
		expect(getTier()).toBe('medium');
	});

	it('ignores the post-seek rebuffer when the user skips around', () => {
		const { controller, getTier, reloadAtCurrentQuality } = setup();
		for (let i = 0; i < 4; i++) {
			controller.notePlaybackRestart(); // seek
			vi.advanceTimersByTime(1_500);
			controller.recordStallAndMaybeDowngrade(); // ffmpeg spin-up stall
			vi.advanceTimersByTime(3_000);
		}
		expect(getTier()).toBe('high');
		expect(reloadAtCurrentQuality).not.toHaveBeenCalled();
	});

	it('drops stalls recorded before a seek', () => {
		const { controller, getTier } = setup();
		controller.recordStallAndMaybeDowngrade();
		controller.notePlaybackRestart();
		vi.advanceTimersByTime(11_000); // past grace, still inside the 20s stall window
		controller.recordStallAndMaybeDowngrade();
		expect(getTier()).toBe('high');
	});

	it('downgrades on a genuine stall pattern once the grace period ends', () => {
		const { controller, getTier } = setup();
		controller.notePlaybackRestart();
		vi.advanceTimersByTime(11_000);
		controller.recordStallAndMaybeDowngrade();
		vi.advanceTimersByTime(4_000);
		controller.recordStallAndMaybeDowngrade();
		expect(getTier()).toBe('medium');
	});

	it('does not read a seek-emptied buffer as a drain', () => {
		const { controller, getTier, bufferedAhead, speedKBs, setMeasuredSpeedMbps } = setup();
		// Healthy playback with a big buffer, at a byte-rate low enough that a
		// real drain would justify a downgrade.
		speedKBs.value = 500; // 4 Mbps < 5 * 1.2
		for (let i = 0; i < 4; i++) {
			controller.sampleThroughput();
			vi.advanceTimersByTime(5_000);
		}
		// Seek: buffer collapses, cold connection reads slow.
		controller.notePlaybackRestart();
		bufferedAhead.value = 0.5;
		speedKBs.value = 200;
		setMeasuredSpeedMbps.mockClear();
		controller.sampleThroughput();
		vi.advanceTimersByTime(5_000);
		controller.sampleThroughput();
		expect(setMeasuredSpeedMbps).toHaveBeenCalled(); // panel stays live during grace
		// Buffer refills after the grace period.
		bufferedAhead.value = 20;
		speedKBs.value = 500;
		for (let i = 0; i < 4; i++) {
			vi.advanceTimersByTime(5_000);
			controller.sampleThroughput();
		}
		expect(getTier()).toBe('high');
	});
});
