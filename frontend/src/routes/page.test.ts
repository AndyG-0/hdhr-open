import { render, screen, fireEvent, within } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const {
	getHDHomeRunChannels,
	getHDHomeRunGuide,
	getNetworkIntegration,
	updateNetworkIntegration,
	listRecordingRules,
	addHDHomeRunRecordingRule,
	deleteHDHomeRunRecordingRule,
	getDvrInfo,
	hdhomerunPlaybackUrl,
	hdhomerunPlaylistUrl,
	hdhomerunRecordingCaptionsUrl,
	hdhomerunRecordingDetail,
	hdhomerunRecordingThumbnailVttUrl,
	hdhomerunRecordingThumbnailSpriteUrl,
} = vi.hoisted(() => ({
	getHDHomeRunChannels: vi.fn(),
	getHDHomeRunGuide: vi.fn(),
	getNetworkIntegration: vi.fn(),
	updateNetworkIntegration: vi.fn(),
	listRecordingRules: vi.fn(),
	addHDHomeRunRecordingRule: vi.fn(),
	deleteHDHomeRunRecordingRule: vi.fn(),
	getDvrInfo: vi.fn(),
	hdhomerunPlaybackUrl: vi.fn((url: string) => `https://example.com/proxy?src=${url}`),
	hdhomerunPlaylistUrl: vi.fn((ch: string) => `https://example.com/playlist/${ch}`),
	hdhomerunRecordingCaptionsUrl: vi.fn((opts: { recordingId: string }) => `https://example.com/captions/${opts.recordingId}.vtt`),
	hdhomerunRecordingDetail: vi.fn().mockResolvedValue({
		is_in_progress: false,
		duration_seconds: 120,
		video: null,
		audio: [],
		has_captions: false,
		transcode: null,
	}),
	hdhomerunRecordingThumbnailVttUrl: vi.fn((opts: { recordingId: string }) => `https://example.com/thumbs/${opts.recordingId}.vtt`),
	hdhomerunRecordingThumbnailSpriteUrl: vi.fn((opts: { recordingId: string }) => `https://example.com/thumbs/${opts.recordingId}.jpg`),
}));

vi.mock('mpegts.js', () => ({
	default: {
		createPlayer: vi.fn(() => ({
			on: vi.fn(),
			attachMediaElement: vi.fn(),
			load: vi.fn(),
			play: vi.fn(),
			pause: vi.fn(),
			unload: vi.fn(),
			detachMediaElement: vi.fn(),
			destroy: vi.fn(),
		})),
		Events: { ERROR: 'error' },
		ErrorTypes: { NETWORK_ERROR: 'NetworkError', MEDIA_ERROR: 'MediaError' },
	},
}));

vi.mock('$lib/api', () => ({
	api: {
		getHDHomeRunChannels,
		getHDHomeRunGuide,
		getNetworkIntegration,
		updateNetworkIntegration,
		listRecordingRules,
		addHDHomeRunRecordingRule,
		deleteHDHomeRunRecordingRule,
		getDvrInfo,
		hdhomerunPlaybackUrl,
		hdhomerunPlaylistUrl,
		hdhomerunRecordingCaptionsUrl,
		hdhomerunRecordingDetail,
		hdhomerunRecordingThumbnailVttUrl,
		hdhomerunRecordingThumbnailSpriteUrl,
	},
}));

import Page from './+page.svelte';

const channel = {
	channel_number: '4.1',
	name: 'KDFW',
	is_hd: true,
	is_drm: false,
	stream_url: 'http://tuner.local/stream/4.1',
	playback_url: '/api/hdhomerun/watch/4.1',
	now: { title: 'Evening News', episode_title: null, start: null, end: null },
	next: { title: 'Nightly Show', episode_title: null, start: null, end: null },
};

const nowSeconds = () => Math.floor(Date.now() / 1000);

const guideWithLiveAiring = () => [
	{
		channel_number: '4.1',
		channel_name: 'KDFW',
		airings: [
			{
				series_id: 'SH123',
				title: 'Evening News',
				episode_title: null,
				start: nowSeconds() - 60,
				end: nowSeconds() + 30 * 60,
			},
		],
	},
];

const integration = (favoriteChannels: string[] = []) => ({
	id: 'hdhomerun',
	type: 'hdhomerun',
	name: 'HDHomeRun',
	settings: { favorite_channels: favoriteChannels },
});

describe('home +page.svelte (guide)', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		localStorage.clear();
		getHDHomeRunGuide.mockResolvedValue([]);
		getNetworkIntegration.mockResolvedValue(integration());
		listRecordingRules.mockResolvedValue([]);
		getDvrInfo.mockResolvedValue({ is_builtin: true });
	});

	it('shows a not-connected hint when there is no tuner', async () => {
		getHDHomeRunChannels.mockRejectedValue(new Error('no tuner'));

		render(Page);

		expect(await screen.findByText('No tuner configured yet — set up HDHomeRun in Settings.')).toBeInTheDocument();
	});

	it('renders the channel lineup with guide entries', async () => {
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());

		render(Page);

		expect(await screen.findByText('Evening News')).toBeInTheDocument();
		expect(screen.getByText('4.1')).toBeInTheDocument();
		expect(screen.getByText('KDFW')).toBeInTheDocument();
	});

	it('shows a guide-unavailable hint when the tuner has no guide data', async () => {
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: false });

		render(Page);

		expect(
			await screen.findByText(
				'Guide unavailable — showing channel lineup only. Program titles require an HDHomeRun DVR subscription.',
			),
		).toBeInTheDocument();
	});

	it('toggles a channel as a favorite and persists it', async () => {
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		updateNetworkIntegration.mockResolvedValue(integration(['4.1']));

		render(Page);

		await fireEvent.click(await screen.findByRole('button', { name: 'Add to favorites' }));

		expect(updateNetworkIntegration).toHaveBeenCalledWith('hdhomerun', { favorite_channels: ['4.1'] });
		expect(await screen.findByRole('button', { name: 'Remove from favorites' })).toBeInTheDocument();
	});

	it('opens the player when a live airing is watched and closes it', async () => {
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());

		render(Page);

		const liveCell = (await screen.findByText('Evening News')).closest('.airing-cell');
		if (!liveCell) throw new Error('live airing cell not found');
		await fireEvent.click(liveCell);

		expect(screen.getByRole('dialog', { name: '4.1 KDFW' })).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Close player' }));

		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
	});

	it('opens the player when clicking the channel in the left column', async () => {
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());

		render(Page);

		const channelNameEl = await screen.findByText('KDFW');
		const channelCol = channelNameEl.closest('.channel-col');
		if (!channelCol) throw new Error('channel-col not found');

		await fireEvent.click(channelCol);

		expect(await screen.findByRole('dialog', { name: '4.1 KDFW' })).toBeInTheDocument();
	});

	it('toggling favorite does not open the player', async () => {
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());
		updateNetworkIntegration.mockResolvedValue(integration(['4.1']));

		render(Page);

		const favBtn = await screen.findByRole('button', { name: 'Add to favorites' });
		await fireEvent.click(favBtn);

		expect(updateNetworkIntegration).toHaveBeenCalledWith('hdhomerun', { favorite_channels: ['4.1'] });
		expect(screen.queryByRole('dialog', { name: '4.1 KDFW' })).not.toBeInTheDocument();
	});

	it('renders channel.now airing when fullGuide is empty', async () => {
		const channelWithLive = {
			...channel,
			now: {
				title: 'Current Live Show',
				episode_title: null,
				start: nowSeconds() - 300,
				end: nowSeconds() + 1800,
			},
		};
		getHDHomeRunChannels.mockResolvedValue({ channels: [channelWithLive], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue([]);

		render(Page);

		expect(await screen.findByText('Current Live Show')).toBeInTheDocument();
	});

	it('merges channel.now airing when fullGuide only contains future airings', async () => {
		const channelWithLive = {
			...channel,
			now: {
				title: 'Current Gap-Fill Show',
				episode_title: null,
				start: nowSeconds() - 300,
				end: nowSeconds() + 1800,
			},
		};
		getHDHomeRunChannels.mockResolvedValue({ channels: [channelWithLive], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue([
			{
				channel_number: '4.1',
				channel_name: 'KDFW',
				airings: [
					{
						title: 'Late Night Show',
						episode_title: null,
						start: nowSeconds() + 7200,
						end: nowSeconds() + 10800,
					},
				],
			},
		]);

		render(Page);

		expect(await screen.findByText('Current Gap-Fill Show')).toBeInTheDocument();
		expect(await screen.findByText('Late Night Show')).toBeInTheDocument();
	});

	it('surfaces the server-provided reason when a series recording rule is rejected', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());
		addHDHomeRunRecordingRule.mockRejectedValue(new Error('no active DVR subscription'));

		render(Page);

		const liveCell = (await screen.findByText('Evening News')).closest('.airing-cell');
		if (!liveCell) throw new Error('live airing cell not found');

		await fireEvent.pointerDown(liveCell);
		await vi.advanceTimersByTimeAsync(500);
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Record Series' }));

		expect(await screen.findByText('no active DVR subscription')).toBeInTheDocument();
		vi.useRealTimers();
	});

	it('sends padding and retention options when scheduling via the recording options dialog', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());
		addHDHomeRunRecordingRule.mockResolvedValue([]);

		render(Page);

		const liveCell = (await screen.findByText('Evening News')).closest('.airing-cell');
		if (!liveCell) throw new Error('live airing cell not found');

		await fireEvent.pointerDown(liveCell);
		await vi.advanceTimersByTimeAsync(500);
		await fireEvent.click(screen.getByRole('menuitem', { name: /Recording options/ }));

		const dialog = await screen.findByRole('dialog', { name: 'Recording Options' });

		await fireEvent.input(within(dialog).getByLabelText('Start early (minutes)'), { target: { value: '5' } });
		await fireEvent.input(within(dialog).getByLabelText('End late (minutes)'), { target: { value: '10' } });
		await fireEvent.click(within(dialog).getByLabelText('Keep last 3'));
		await fireEvent.input(within(dialog).getByLabelText('Episodes to keep'), { target: { value: '2' } });

		await fireEvent.click(within(dialog).getByRole('button', { name: 'Record Series' }));

		expect(addHDHomeRunRecordingRule).toHaveBeenCalledWith({
			series_id: 'SH123',
			channel: '4.1',
			title: 'Evening News',
			title_match_mode: 'exact',
			keyword_query: undefined,
			start_padding: 300,
			end_padding: 600,
			recent_only: undefined,
			max_episodes_to_keep: 2,
			server: undefined,
		});
		vi.useRealTimers();
	});

	it('shows a pending badge for a newly created rule until a later fetch confirms it', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());
		const newRule = { RecordingRuleID: 'new-1', SeriesID: 'SH123', Title: 'Evening News' };
		addHDHomeRunRecordingRule.mockResolvedValue([newRule]);
		// Simulates SiliconDust's cloud API being eventually consistent: the
		// very next rules fetch doesn't include the newly created rule yet.
		listRecordingRules.mockResolvedValue([]);

		render(Page);

		const liveCell = (await screen.findByText('Evening News')).closest('.airing-cell');
		if (!liveCell) throw new Error('live airing cell not found');

		await fireEvent.pointerDown(liveCell);
		await vi.advanceTimersByTimeAsync(500);
		await fireEvent.click(screen.getByRole('menuitem', { name: 'Record Series' }));

		await vi.waitFor(() => expect(addHDHomeRunRecordingRule).toHaveBeenCalled());

		expect(await screen.findByText('⏳ Pending')).toBeInTheDocument();
		vi.useRealTimers();
	});

	it('keeps showing a pending rule as pending after a reload, until a fresh fetch confirms it', async () => {
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());
		const newRule = { RecordingRuleID: 'new-1', SeriesID: 'SH123', Title: 'Evening News' };
		localStorage.setItem('hdhomerun-pending-rules', JSON.stringify([{ rule: newRule, createdAt: Date.now() }]));
		listRecordingRules.mockResolvedValue([]);

		render(Page);

		expect(await screen.findByText('⏳ Pending')).toBeInTheDocument();
	});

	it('does not show a stale pending rule older than the max age', async () => {
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());
		const oldRule = { RecordingRuleID: 'old-1', SeriesID: 'SH123', Title: 'Evening News' };
		localStorage.setItem(
			'hdhomerun-pending-rules',
			JSON.stringify([{ rule: oldRule, createdAt: Date.now() - 60 * 60 * 1000 }]),
		);
		listRecordingRules.mockResolvedValue([]);

		render(Page);

		await screen.findByText('Evening News');
		expect(screen.queryByText('⏳ Pending')).not.toBeInTheDocument();
	});

	it('allows recording the currently playing program from the video player', async () => {
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getHDHomeRunGuide.mockResolvedValue(guideWithLiveAiring());
		listRecordingRules.mockResolvedValue([]);
		addHDHomeRunRecordingRule.mockResolvedValue([
			{ RecordingRuleID: 'rule-live-1', SeriesID: 'SH123', Title: 'Evening News' },
		]);

		render(Page);

		const liveCell = (await screen.findByText('Evening News')).closest('.airing-cell');
		if (!liveCell) throw new Error('live airing cell not found');

		// Click live cell to start watching
		await fireEvent.click(liveCell);

		// Player overlay is opened
		const playerDialog = await screen.findByRole('dialog', { name: '4.1 KDFW' });
		expect(playerDialog).toBeInTheDocument();

		// Record button is in player header
		const recordBtn = within(playerDialog).getByRole('button', { name: /Record/i });
		await fireEvent.click(recordBtn);

		// Popover shows Record Series
		const seriesBtn = within(playerDialog).getByRole('button', { name: 'Record Series' });
		await fireEvent.click(seriesBtn);

		await vi.waitFor(() =>
			expect(addHDHomeRunRecordingRule).toHaveBeenCalledWith({
				series_id: 'SH123',
				channel: '4.1',
				start_padding: undefined,
				end_padding: undefined,
				recent_only: undefined,
				max_episodes_to_keep: undefined,
				server: undefined,
			}),
		);
	});
});
