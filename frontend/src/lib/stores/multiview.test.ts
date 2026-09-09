import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';

const {
	startWatch,
	heartbeatWatch,
	stopWatch,
	getTunerStatus,
	getTunerInfo,
	hdhomerunPlaybackUrl,
	hdhomerunRecordingStreamUrl,
} = vi.hoisted(() => ({
	startWatch: vi.fn(),
	heartbeatWatch: vi.fn().mockResolvedValue(undefined),
	stopWatch: vi.fn(),
	getTunerStatus: vi.fn().mockResolvedValue([]),
	getTunerInfo: vi.fn().mockResolvedValue({ friendly_name: 'HDHomeRun CONNECT', tuner_count: 2 }),
	hdhomerunPlaybackUrl: vi.fn((url: string) => `http://localhost:8000${url}`),
	hdhomerunRecordingStreamUrl: vi.fn((url: string) => `http://localhost:8000/api/dvr/recording-stream?url=${encodeURIComponent(url)}`),
}));

vi.mock('$lib/api', () => ({
	api: {
		startWatch,
		heartbeatWatch,
		stopWatch,
		getTunerStatus,
		getTunerInfo,
		hdhomerunPlaybackUrl,
		hdhomerunRecordingStreamUrl,
	},
}));

import {
	multiview,
	addFeed,
	removeFeed,
	replaceFeed,
	setAudioSlot,
	swapSlots,
	setLayout,
	expandSlot,
	closeAll,
	recommendedLayout,
	maxSlotsForLayout,
	availableLayouts,
	initTunerCapacity,
	evaluateTunerAvailability,
} from './multiview';

const mockChannel = (num: string, name: string) => ({
	channel_number: num,
	name,
	is_hd: true,
	is_drm: false,
	stream_url: '',
	playback_url: `/auto/v${num}`,
	now: {
		title: `${name} Live Show`,
		episode_title: null,
		start: 1000,
		end: 2000,
		series_id: null,
		channel_number: num,
	},
	next: null,
});

describe('multiview store', () => {
	beforeEach(() => {
		closeAll();
		vi.clearAllMocks();
		startWatch.mockImplementation(async (channelNumber: string) => ({
			recording_id: `rec_${channelNumber}`,
			session_id: `watch_${channelNumber}`,
			playUrl: `/recorded/rec_${channelNumber}`,
		}));
		getTunerInfo.mockResolvedValue({ friendly_name: 'HDHomeRun CONNECT', tuner_count: 2 });
		getTunerStatus.mockResolvedValue([
			{ index: 0, in_use: false, channel_number: null },
			{ index: 1, in_use: false, channel_number: null },
		]);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('has clean initial state with 2-tuner default', () => {
		const state = get(multiview);
		expect(state.active).toBe(false);
		expect(state.slots).toHaveLength(0);
		expect(state.activeSlotIndex).toBe(0);
		expect(state.layout).toBe('side_by_side');
		expect(state.totalTuners).toBe(2);
		expect(state.maxFeeds).toBe(2);
	});

	it('computes correct recommended layout and available layout filtering', () => {
		expect(availableLayouts(2)).toEqual(['side_by_side']);
		expect(availableLayouts(3)).toEqual(['side_by_side', 'three_box']);
		expect(availableLayouts(4)).toEqual(['side_by_side', 'three_box', 'quad']);

		expect(recommendedLayout(1, 2)).toBe('side_by_side');
		expect(recommendedLayout(2, 2)).toBe('side_by_side');
		expect(recommendedLayout(3, 2)).toBe('side_by_side'); // Clamped for 2 feeds
		expect(recommendedLayout(3, 4)).toBe('three_box');
		expect(recommendedLayout(4, 4)).toBe('quad');

		expect(maxSlotsForLayout('side_by_side')).toBe(2);
		expect(maxSlotsForLayout('three_box')).toBe(3);
		expect(maxSlotsForLayout('quad')).toBe(4);
	});

	it('initializes capacity from tuner info', async () => {
		getTunerInfo.mockResolvedValueOnce({ friendly_name: 'HDHomeRun FLEX 4K', tuner_count: 4 });
		const feeds = await initTunerCapacity();
		expect(feeds).toBe(4);
		const state = get(multiview);
		expect(state.totalTuners).toBe(4);
		expect(state.maxFeeds).toBe(4);
	});

	it('adds first feed and un-mutes it by default', async () => {
		const channel = mockChannel('2.1', 'KDFW');
		const slotId = await addFeed(channel);

		const state = get(multiview);
		expect(state.active).toBe(true);
		expect(state.slots).toHaveLength(1);
		expect(state.slots[0].id).toBe(slotId);
		expect(state.slots[0].channel.channel_number).toBe('2.1');
		expect(state.slots[0].isMuted).toBe(false);
		expect(state.slots[0].watchSessionId).toBe('watch_2.1');
		expect(state.activeSlotIndex).toBe(0);
		expect(startWatch).toHaveBeenCalledWith('2.1');
	});

	it('enforces 2-feed limit for 2-tuner setups and rejects 3rd feed', async () => {
		await addFeed(mockChannel('2.1', 'KDFW'));
		await addFeed(mockChannel('4.1', 'KXAS'));

		expect(get(multiview).slots).toHaveLength(2);
		await expect(addFeed(mockChannel('5.1', 'WFAA'))).rejects.toThrow(
			'Maximum of 2 concurrent feeds reached.',
		);
	});

	it('allows up to 4 feeds when 4 tuners are available', async () => {
		getTunerInfo.mockResolvedValue({ friendly_name: 'HDHomeRun FLEX 4K', tuner_count: 4 });
		getTunerStatus.mockResolvedValue([
			{ index: 0, in_use: false },
			{ index: 1, in_use: false },
			{ index: 2, in_use: false },
			{ index: 3, in_use: false },
		]);
		await initTunerCapacity();

		await addFeed(mockChannel('2.1', 'KDFW'));
		await addFeed(mockChannel('4.1', 'KXAS'));
		expect(get(multiview).layout).toBe('side_by_side');

		await addFeed(mockChannel('5.1', 'WFAA'));
		expect(get(multiview).layout).toBe('three_box');

		await addFeed(mockChannel('11.1', 'KTVT'));
		expect(get(multiview).layout).toBe('quad');
		expect(get(multiview).slots).toHaveLength(4);

		await expect(addFeed(mockChannel('13.1', 'KERA'))).rejects.toThrow(
			'Maximum of 4 concurrent feeds reached.',
		);
	});

	it('allows tuning a channel that is currently recording even when all tuners are busy (tuner sharing)', async () => {
		getTunerStatus.mockResolvedValue([
			{
				index: 0,
				in_use: true,
				channel_number: '4.1',
				channel_name: 'NBC 5',
				client: {
					type: 'scheduled_recording',
					name: 'Recording: Evening News',
					is_recording: true,
					recording_id: 'rec_news',
					details: "Scheduled recording 'Evening News'",
					viewers: [],
				},
			},
			{
				index: 1,
				in_use: true,
				channel_number: '5.1',
				channel_name: 'WFAA',
				client: {
					type: 'live_watch',
					name: 'Living Room TV',
					is_recording: false,
					recording_id: null,
					details: 'Live TV on 5.1',
					viewers: [],
				},
			},
		]);

		// Channel 4.1 is recording -> shared tuner -> allowed
		const availRecording = await evaluateTunerAvailability('4.1');
		expect(availRecording.available).toBe(true);
		expect(availRecording.isShared).toBe(true);

		// Channel 7.1 is not recording/streaming -> requires new tuner -> unavailable with rich explanation
		const availNew = await evaluateTunerAvailability('7.1');
		expect(availNew.available).toBe(false);
		expect(availNew.isShared).toBe(false);
		expect(availNew.explanation).toContain('All 2 tuners are currently in use');
		expect(availNew.explanation).toContain('Recording: Evening News (Ch 4.1)');
		expect(availNew.explanation).toContain('Ch 5.1 (Living Room TV)');
		expect(availNew.explanation).toContain('You can watch Ch 4.1 without consuming another tuner');
	});

	it('sets rich error on slot when tuning an unavailable channel with exhausted tuners', async () => {
		getTunerStatus.mockResolvedValue([
			{ index: 0, in_use: true, channel_number: '2.1', client: { is_recording: true, name: 'Recording: Local News' } },
			{ index: 1, in_use: true, channel_number: '4.1', client: { is_recording: false, name: 'Web Viewer' } },
		]);

		const slotId = await addFeed(mockChannel('9.1', 'FOX'));
		const state = get(multiview);
		expect(state.slots[0].id).toBe(slotId);
		expect(state.slots[0].error).toContain('All 2 tuners are currently in use');
		expect(state.slots[0].loading).toBe(false);
	});

	it('switches audio focus and ensures exactly one unmuted slot', async () => {
		getTunerInfo.mockResolvedValue({ friendly_name: 'HDHomeRun FLEX 4K', tuner_count: 4 });
		await initTunerCapacity();

		await addFeed(mockChannel('2.1', 'KDFW'));
		await addFeed(mockChannel('4.1', 'KXAS'));
		await addFeed(mockChannel('5.1', 'WFAA'));

		setAudioSlot(1);
		let state = get(multiview);
		expect(state.activeSlotIndex).toBe(1);
		expect(state.slots[0].isMuted).toBe(true);
		expect(state.slots[1].isMuted).toBe(false);
		expect(state.slots[2].isMuted).toBe(true);

		setAudioSlot(2);
		state = get(multiview);
		expect(state.activeSlotIndex).toBe(2);
		expect(state.slots[0].isMuted).toBe(true);
		expect(state.slots[1].isMuted).toBe(true);
		expect(state.slots[2].isMuted).toBe(false);
	});

	it('swaps slots in the grid and maintains audio focus with moved slot', async () => {
		getTunerInfo.mockResolvedValue({ friendly_name: 'HDHomeRun FLEX 4K', tuner_count: 4 });
		await initTunerCapacity();

		await addFeed(mockChannel('2.1', 'KDFW'));
		await addFeed(mockChannel('4.1', 'KXAS'));
		await addFeed(mockChannel('5.1', 'WFAA'));

		swapSlots(2, 0);
		let state = get(multiview);
		expect(state.slots[0].channel.channel_number).toBe('5.1');
		expect(state.slots[2].channel.channel_number).toBe('2.1');
		expect(state.activeSlotIndex).toBe(2);
		expect(state.slots[2].isMuted).toBe(false);
		expect(state.slots[0].isMuted).toBe(true);
	});

	it('replaces a feed in place, tearing down old watch session and starting new one', async () => {
		await addFeed(mockChannel('2.1', 'KDFW'));
		await replaceFeed(0, mockChannel('8.1', 'WFAA'));

		expect(stopWatch).toHaveBeenCalledWith('watch_2.1');
		expect(startWatch).toHaveBeenCalledWith('8.1');

		const state = get(multiview);
		expect(state.slots[0].channel.channel_number).toBe('8.1');
		expect(state.slots[0].watchSessionId).toBe('watch_8.1');
	});

	it('removes a feed, tears down session, and adapts layout', async () => {
		getTunerInfo.mockResolvedValue({ friendly_name: 'HDHomeRun FLEX 4K', tuner_count: 4 });
		await initTunerCapacity();

		await addFeed(mockChannel('2.1', 'KDFW'));
		await addFeed(mockChannel('4.1', 'KXAS'));
		await addFeed(mockChannel('5.1', 'WFAA'));
		await addFeed(mockChannel('11.1', 'KTVT'));

		setAudioSlot(2);
		removeFeed(1); // remove KXAS

		expect(stopWatch).toHaveBeenCalledWith('watch_4.1');
		let state = get(multiview);
		expect(state.slots).toHaveLength(3);
		expect(state.activeSlotIndex).toBe(1);
		expect(state.slots[1].channel.channel_number).toBe('5.1');
		expect(state.slots[1].isMuted).toBe(false);
		expect(state.layout).toBe('three_box');

		removeFeed(0); // remove KDFW
		state = get(multiview);
		expect(state.slots).toHaveLength(2);
		expect(state.layout).toBe('side_by_side');
	});

	it('closes all feeds and cleans up all sessions', async () => {
		await addFeed(mockChannel('2.1', 'KDFW'));
		await addFeed(mockChannel('4.1', 'KXAS'));

		closeAll();

		expect(stopWatch).toHaveBeenCalledWith('watch_2.1');
		expect(stopWatch).toHaveBeenCalledWith('watch_4.1');

		const state = get(multiview);
		expect(state.active).toBe(false);
		expect(state.slots).toHaveLength(0);
	});

	it('handles expandSlot correctly', async () => {
		await addFeed(mockChannel('2.1', 'KDFW'));
		await addFeed(mockChannel('4.1', 'KXAS'));

		expandSlot(1);
		let state = get(multiview);
		expect(state.expandedSlotIndex).toBe(1);
		expect(state.activeSlotIndex).toBe(1);
		expect(state.slots[1].isMuted).toBe(false);
		expect(state.slots[0].isMuted).toBe(true);

		expandSlot(null);
		state = get(multiview);
		expect(state.expandedSlotIndex).toBeNull();
	});
});

