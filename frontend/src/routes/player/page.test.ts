import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const {
	goto,
	pageState,
	startWatch,
	stopWatch,
	heartbeatWatch,
	getHDHomeRunChannels,
	getHDHomeRunGuide,
	listRecordings,
	getNetworkIntegration,
	getDvrInfo,
	listRecordingRules,
	hdhomerunPlaybackUrl,
	hdhomerunRecordingStreamUrl,
	hdhomerunRecordingDetail,
	hdhomerunRecordingCaptionsUrl,
	hdhomerunRecordingThumbnailVttUrl,
	hdhomerunRecordingThumbnailSpriteUrl,
} = vi.hoisted(() => ({
	goto: vi.fn(),
	pageState: { url: new URL('http://localhost/player') },
	startWatch: vi.fn(),
	stopWatch: vi.fn(),
	heartbeatWatch: vi.fn(),
	getHDHomeRunChannels: vi.fn(),
	getHDHomeRunGuide: vi.fn(),
	listRecordings: vi.fn(),
	getNetworkIntegration: vi.fn(),
	getDvrInfo: vi.fn(),
	listRecordingRules: vi.fn(),
	hdhomerunPlaybackUrl: vi.fn((url: string) => `http://localhost/playback?url=${url}`),
	hdhomerunRecordingStreamUrl: vi.fn((url: string) => `http://localhost/stream?url=${url}`),
	hdhomerunRecordingCaptionsUrl: vi.fn((opts: { recordingId: string }) => `http://localhost/captions/${opts.recordingId}.vtt`),
	hdhomerunRecordingThumbnailVttUrl: vi.fn((opts: { recordingId: string }) => `http://localhost/thumbs/${opts.recordingId}.vtt`),
	hdhomerunRecordingThumbnailSpriteUrl: vi.fn((opts: { recordingId: string }) => `http://localhost/thumbs/${opts.recordingId}.jpg`),
	hdhomerunRecordingDetail: vi.fn().mockResolvedValue({
		is_in_progress: false,
		duration_seconds: 120,
		video: null,
		audio: [],
		has_captions: false,
		transcode: null,
	}),
}));

class FakeVTTCue {
	constructor(
		public startTime: number,
		public endTime: number,
		public text: string,
	) {}
}
(globalThis as unknown as { VTTCue: typeof FakeVTTCue }).VTTCue = FakeVTTCue;

vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$app/state', () => ({ page: pageState }));
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
		startWatch,
		stopWatch,
		heartbeatWatch,
		getHDHomeRunChannels,
		getHDHomeRunGuide,
		listRecordings,
		getNetworkIntegration,
		getDvrInfo,
		listRecordingRules,
		hdhomerunPlaybackUrl,
		hdhomerunRecordingStreamUrl,
		hdhomerunRecordingDetail,
		hdhomerunRecordingCaptionsUrl,
		hdhomerunRecordingThumbnailVttUrl,
		hdhomerunRecordingThumbnailSpriteUrl,
		createHDHomeRunRecordingRule: vi.fn(),
		deleteHDHomeRunRecordingRule: vi.fn(),
		updateHDHomeRunRecordingRule: vi.fn(),
		updateNetworkIntegration: vi.fn(),
	},
}));

import PopoutPlayerPage from './+page.svelte';

describe('/player route', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		pageState.url = new URL('http://localhost/player');
		getNetworkIntegration.mockResolvedValue({ settings: { favorite_channels: [], playback_mode: 'server_transcode' } });
		getDvrInfo.mockResolvedValue({ is_builtin: true });
		listRecordingRules.mockResolvedValue([]);
		getHDHomeRunChannels.mockResolvedValue({
			channels: [
				{
					channel_number: '5.1',
					name: 'NBC',
					playback_url: '/auto/v5.1',
					is_hd: true,
					is_drm: false,
					stream_url: '',
					now: null,
					next: null,
				},
			],
			guide_available: true,
		});
		getHDHomeRunGuide.mockResolvedValue([]);
		listRecordings.mockResolvedValue([]);
	});

	it('renders error state when no stream parameter is specified', async () => {
		render(PopoutPlayerPage);
		expect(await screen.findByText(/No channel, recording, or play_url specified/i)).toBeInTheDocument();
	});

	it('loads channel and manages watch session lifecycle with heartbeats and stopWatch on unmount', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		try {
			pageState.url = new URL('http://localhost/player?channel=5.1');
			startWatch.mockResolvedValue({
				recording_id: 'rec-watch-123',
				session_id: 'sess-watch-456',
				play_url: '/recorded/rec-watch-123',
				start: 1000,
			});
			heartbeatWatch.mockResolvedValue(undefined);

			const { unmount } = render(PopoutPlayerPage);

			await waitFor(() => expect(startWatch).toHaveBeenCalledWith('5.1'));
			expect(await screen.findByRole('dialog', { name: /5.1 NBC/i })).toBeInTheDocument();

			// Fast-forward 20s: should trigger heartbeat
			vi.advanceTimersByTime(20_000);
			expect(heartbeatWatch).toHaveBeenCalledWith('sess-watch-456');

			// Unmount should stop the watch session
			unmount();
			expect(stopWatch).toHaveBeenCalledWith('sess-watch-456');
		} finally {
			vi.useRealTimers();
		}
	});

	it('calls stopWatch on pagehide event', async () => {
		pageState.url = new URL('http://localhost/player?channel=5.1');
		startWatch.mockResolvedValue({
			recording_id: 'rec-watch-123',
			session_id: 'sess-watch-456',
			play_url: '/recorded/rec-watch-123',
			start: 1000,
		});

		render(PopoutPlayerPage);
		await waitFor(() => expect(startWatch).toHaveBeenCalledWith('5.1'));

		window.dispatchEvent(new Event('pagehide'));
		expect(stopWatch).toHaveBeenCalledWith('sess-watch-456');
	});

	it('falls back to plain live streaming if startWatch fails', async () => {
		pageState.url = new URL('http://localhost/player?channel=5.1');
		startWatch.mockRejectedValue(new Error('No tuner available'));

		render(PopoutPlayerPage);

		expect(await screen.findByRole('dialog', { name: /5.1 NBC/i })).toBeInTheDocument();
		expect(stopWatch).not.toHaveBeenCalled();
	});

	it('loads recording media when ?recording=rec-99 is provided', async () => {
		pageState.url = new URL('http://localhost/player?recording=rec-99');
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-99',
				title: 'Nova',
				episode_title: 'Planets',
				is_dvr_file: true,
				play_url: '/recorded/rec-99',
				start: 100,
				record_end: 200,
			},
		]);

		render(PopoutPlayerPage);

		expect(await screen.findByRole('dialog', { name: /Nova - Planets/i })).toBeInTheDocument();
		expect(hdhomerunRecordingStreamUrl).toHaveBeenCalledWith('/recorded/rec-99');
	});

	it('loads direct play media when ?play_url is provided', async () => {
		pageState.url = new URL('http://localhost/player?play_url=%2Frecorded%2Fcustom-stream&title=Custom+Title');

		render(PopoutPlayerPage);

		expect(await screen.findByRole('dialog', { name: /Custom Title/i })).toBeInTheDocument();
	});

	it('handleClose closes window when window.opener is present', async () => {
		pageState.url = new URL('http://localhost/player?channel=5.1');
		startWatch.mockResolvedValue({
			recording_id: 'rec-1',
			session_id: 'sess-1',
		});

		const closeSpy = vi.fn();
		vi.stubGlobal('opener', {});
		vi.stubGlobal('close', closeSpy);

		render(PopoutPlayerPage);

		const backBtn = await screen.findByRole('button', { name: /Close player/i });
		await fireEvent.click(backBtn);

		expect(stopWatch).toHaveBeenCalledWith('sess-1');
		expect(closeSpy).toHaveBeenCalled();
	});
});
