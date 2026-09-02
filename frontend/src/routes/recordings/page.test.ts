import { render, screen, fireEvent, within } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const {
	getDvrInfo,
	listRecordings,
	listRecordingRules,
	getHDHomeRunChannels,
	getNetworkIntegration,
	deleteHDHomeRunRecordingRule,
	deleteRecording,
	addHDHomeRunRecordingRule,
	getTunerInfo,
	getTunerStatus,
	terminateTuner,
	hdhomerunRecordingStreamUrl,
	hdhomerunPlaybackUrl,
	hdhomerunPlaylistUrl,
	hdhomerunRecordingCaptionsUrl,
	hdhomerunRecordingDetail,
	hdhomerunRecordingThumbnailVttUrl,
	hdhomerunRecordingThumbnailSpriteUrl,
} = vi.hoisted(() => ({
	getDvrInfo: vi.fn(),
	listRecordings: vi.fn(),
	listRecordingRules: vi.fn(),
	getHDHomeRunChannels: vi.fn(),
	getNetworkIntegration: vi.fn(),
	deleteHDHomeRunRecordingRule: vi.fn(),
	deleteRecording: vi.fn(),
	addHDHomeRunRecordingRule: vi.fn(),
	getTunerInfo: vi.fn(),
	getTunerStatus: vi.fn(),
	terminateTuner: vi.fn(),
	hdhomerunRecordingStreamUrl: vi.fn((playUrl: string) => `https://example.com/recording-stream?url=${playUrl}`),
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
		getDvrInfo,
		listRecordings,
		listRecordingRules,
		getHDHomeRunChannels,
		getNetworkIntegration,
		deleteHDHomeRunRecordingRule,
		deleteRecording,
		addHDHomeRunRecordingRule,
		getTunerInfo,
		getTunerStatus,
		terminateTuner,
		hdhomerunRecordingStreamUrl,
		hdhomerunPlaybackUrl,
		hdhomerunPlaylistUrl,
		hdhomerunRecordingCaptionsUrl,
		hdhomerunRecordingDetail,
		hdhomerunRecordingThumbnailVttUrl,
		hdhomerunRecordingThumbnailSpriteUrl,
	},
}));

import Page from './+page.svelte';

const nowSeconds = () => Math.floor(Date.now() / 1000);

const channel = {
	channel_number: '4.1',
	name: 'KDFW',
	is_hd: true,
	is_drm: false,
	stream_url: 'http://tuner.local/stream/4.1',
	playback_url: '/api/hdhomerun/watch/4.1',
	now: null,
	next: null,
};

const integration = (playbackMode = 'server_transcode') => ({
	id: 'hdhomerun',
	type: 'hdhomerun',
	name: 'HDHomeRun',
	settings: { playback_mode: playbackMode },
});

describe('recordings +page.svelte', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getDvrInfo.mockResolvedValue(null);
		listRecordings.mockResolvedValue([]);
		listRecordingRules.mockResolvedValue([]);
		getHDHomeRunChannels.mockResolvedValue({ channels: [channel], guide_available: true });
		getNetworkIntegration.mockResolvedValue(integration());
		getTunerInfo.mockResolvedValue(null);
		getTunerStatus.mockResolvedValue([]);
	});

	it('shows a not-connected hint when there is no tuner', async () => {
		getHDHomeRunChannels.mockRejectedValue(new Error('no tuner'));

		render(Page);

		expect(await screen.findByText('No tuner configured yet — set up HDHomeRun in Settings.')).toBeInTheDocument();
	});

	it('shows the DVR free-space hint', async () => {
		getDvrInfo.mockResolvedValue({ friendly_name: 'DVR', version: '1.0', free_space_bytes: 500_000_000_000 });

		render(Page);

		expect(await screen.findByText('Free space: 500.0 GB')).toBeInTheDocument();
	});

	it('splits recordings into in-progress and completed based on record_end', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-live',
				title: 'Big Game',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 600,
				record_end: null,
				is_dvr_file: true,
			},
			{
				recording_id: 'rec-done',
				title: 'Finished Show',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 7200,
				record_end: nowSeconds() - 3600,
				is_dvr_file: true,
			},
		]);

		render(Page);

		expect(await screen.findByText('Big Game')).toBeInTheDocument();
		expect(screen.getByText('● Recording')).toBeInTheDocument();
		expect(screen.getByText('Recording in progress — available to watch once finished.')).toBeInTheDocument();
		expect(screen.getByText('Finished Show')).toBeInTheDocument();

		// The in-progress card should not offer the recorded-file watch button.
		const bigGameCard = screen.getByText('Big Game').closest('.recording');
		expect(bigGameCard).not.toBeNull();
		expect(within(bigGameCard as HTMLElement).queryByRole('button', { name: /Watch$/ })).toBeNull();

		// Nor should it offer a delete button — only completed recordings can be deleted.
		expect(within(bigGameCard as HTMLElement).queryByRole('button', { name: 'Delete' })).toBeNull();

		const finishedShowCard = screen.getByText('Finished Show').closest('.recording');
		expect(finishedShowCard).not.toBeNull();
		expect(within(finishedShowCard as HTMLElement).getByRole('button', { name: 'Delete' })).toBeInTheDocument();
	});

	it('deletes a completed recording', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-done',
				title: 'Finished Show',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 7200,
				record_end: nowSeconds() - 3600,
				is_dvr_file: true,
			},
		]);
		deleteRecording.mockResolvedValue({ status: 'deleted' });

		render(Page);

		expect(await screen.findByText('Finished Show')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

		expect(deleteRecording).toHaveBeenCalledWith('rec-done');
		await vi.waitFor(() => expect(screen.queryByText('Finished Show')).not.toBeInTheDocument());
	});

	it('shows an error and keeps the recording when deleting fails', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-done',
				title: 'Finished Show',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 7200,
				record_end: nowSeconds() - 3600,
				is_dvr_file: true,
			},
		]);
		deleteRecording.mockRejectedValue(new Error('Recording is still in progress'));

		render(Page);

		expect(await screen.findByText('Finished Show')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

		expect(await screen.findByText('Recording is still in progress')).toBeInTheDocument();
		expect(screen.getByText('Finished Show')).toBeInTheDocument();
	});

	it('offers a Watch Live button for an in-progress recording and opens the player', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-live',
				title: 'Big Game',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 600,
				record_end: null,
				is_dvr_file: true,
			},
		]);

		render(Page);

		const watchLiveBtn = await screen.findByRole('button', { name: '▶ Watch Live' });
		await fireEvent.click(watchLiveBtn);

		expect(screen.getByRole('dialog', { name: '4.1 KDFW' })).toBeInTheDocument();
	});

	it('marks a completed DVR-file recording as seekable in server_transcode mode', async () => {
		getNetworkIntegration.mockResolvedValue(integration('server_transcode'));
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-done',
				title: 'Finished Show',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 7200,
				record_end: nowSeconds() - 3600,
				is_dvr_file: true,
				play_url: '/recorded/rec-done',
			},
		]);

		render(Page);

		await fireEvent.click(await screen.findByRole('button', { name: '▶ ▶ Watch' }));

		expect(hdhomerunRecordingStreamUrl).toHaveBeenCalledWith('/recorded/rec-done');
		expect(screen.getByRole('dialog', { name: 'Finished Show' })).toBeInTheDocument();
		expect(screen.getByRole('slider')).toBeInTheDocument();
	});

	it('does not mark a recording as seekable when playback mode is external-player-only', async () => {
		getNetworkIntegration.mockResolvedValue(integration('external'));
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-done',
				title: 'Finished Show',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 7200,
				record_end: nowSeconds() - 3600,
				is_dvr_file: true,
				play_url: '/recorded/rec-done',
			},
		]);

		render(Page);

		await fireEvent.click(await screen.findByRole('button', { name: '▶ ▶ Watch' }));

		expect(screen.getByRole('dialog', { name: 'Finished Show' })).toBeInTheDocument();
		expect(screen.queryByRole('slider')).not.toBeInTheDocument();
	});

	it('shows scheduled recording rules and cancels one', async () => {
		const rule = { RecordingRuleID: 'rule-1', SeriesID: 'SH123', Title: 'Evening News', ChannelOnly: '4.1' };
		listRecordingRules.mockResolvedValue([rule]);
		deleteHDHomeRunRecordingRule.mockResolvedValue([]);

		render(Page);

		expect(await screen.findByText('Evening News')).toBeInTheDocument();
		expect(screen.getByText('Series Rule')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

		expect(deleteHDHomeRunRecordingRule).toHaveBeenCalledWith('rule-1');
		await screen.findByText('No scheduled recordings.');
	});

	it('shows padding and retention summaries on a rule card when set', async () => {
		const rule = {
			RecordingRuleID: 'rule-1',
			SeriesID: 'SH123',
			Title: 'Evening News',
			ChannelOnly: '4.1',
			StartPadding: 300,
			EndPadding: 600,
			MaxEpisodesToKeep: 2,
		};
		listRecordingRules.mockResolvedValue([rule]);

		render(Page);

		expect(await screen.findByText('Evening News')).toBeInTheDocument();
		expect(screen.getByText('+5m / +10m padding')).toBeInTheDocument();
		expect(screen.getByText('Keeps last 2 episodes')).toBeInTheDocument();
	});

	it('omits padding and retention summaries on a rule card when unset', async () => {
		const rule = { RecordingRuleID: 'rule-1', SeriesID: 'SH123', Title: 'Evening News', ChannelOnly: '4.1' };
		listRecordingRules.mockResolvedValue([rule]);

		render(Page);

		expect(await screen.findByText('Evening News')).toBeInTheDocument();
		expect(screen.queryByText(/padding/)).not.toBeInTheDocument();
		expect(screen.queryByText(/Keeps last/)).not.toBeInTheDocument();
	});

	it('shows a no-scheduled-recordings hint when there are none', async () => {
		render(Page);

		expect(await screen.findByText('No scheduled recordings.')).toBeInTheDocument();
	});

	it('displays tuner status with an active channel and an idle tuner', async () => {
		getTunerInfo.mockResolvedValue({
			friendly_name: 'HDHomeRun Connect',
			model_number: 'HDHR5-2US',
			firmware_version: '20231218',
			tuner_count: 2,
		});
		getTunerStatus.mockResolvedValue([
			{
				index: 0,
				in_use: true,
				channel_number: '4.1',
				channel_name: 'KDFW',
				target_ip: '192.168.1.150',
				client: {
					type: 'external',
					name: '192.168.1.150',
					ip: '192.168.1.150',
					hostname: 'plex.local',
					details: 'External stream to 192.168.1.150',
					recording_id: null,
					scheduled_id: null,
					is_recording: false,
					viewers: [],
				},
				warning: {
					severity: 'warning',
					message: 'Tuner 0 is streaming to external client 192.168.1.150. Terminating will clear the tuner lock.',
				},
				signal_strength_percent: 95,
				signal_quality_percent: 100,
				symbol_quality_percent: 100,
				network_rate_bps: 19_000_000,
			},
			{
				index: 1,
				in_use: false,
				channel_number: null,
				channel_name: null,
				target_ip: null,
				client: null,
				warning: null,
				signal_strength_percent: null,
				signal_quality_percent: null,
				symbol_quality_percent: null,
				network_rate_bps: null,
			},
		]);

		render(Page);

		expect(await screen.findByText('2 tuners')).toBeInTheDocument();
		const popover = screen.getByRole('tooltip');
		expect(within(popover).getByText('Tuner Status')).toBeInTheDocument();
		expect(within(popover).getByText('Tuner 0')).toBeInTheDocument();
		expect(within(popover).getByText('4.1')).toBeInTheDocument();
		expect(within(popover).getByText('KDFW')).toBeInTheDocument();
		expect(within(popover).getByText('External: 192.168.1.150')).toBeInTheDocument();
		expect(within(popover).getByText('Signal 95%')).toBeInTheDocument();
		expect(within(popover).getByText('Terminate')).toBeInTheDocument();
		expect(within(popover).getByText('Tuner 1')).toBeInTheDocument();
		expect(within(popover).getByText('Idle')).toBeInTheDocument();
	});

	it('allows terminating an active tuner after confirmation', async () => {
		getTunerInfo.mockResolvedValue({
			friendly_name: 'HDHomeRun Connect',
			model_number: 'HDHR5-2US',
			firmware_version: '20231218',
			tuner_count: 2,
		});
		getTunerStatus.mockResolvedValue([
			{
				index: 0,
				in_use: true,
				channel_number: '4.1',
				channel_name: 'KDFW',
				target_ip: '192.168.1.150',
				client: {
					type: 'external',
					name: '192.168.1.150',
					ip: '192.168.1.150',
					hostname: null,
					details: 'External stream to 192.168.1.150',
					recording_id: null,
					scheduled_id: null,
					is_recording: false,
					viewers: [],
				},
				warning: {
					severity: 'warning',
					message: 'Tuner 0 is streaming to external client 192.168.1.150. Terminating will clear the tuner lock.',
				},
				signal_strength_percent: 95,
				signal_quality_percent: 100,
				symbol_quality_percent: 100,
				network_rate_bps: 19_000_000,
			},
		]);
		terminateTuner.mockResolvedValue({
			ok: true,
			message: 'Tuner 0 released successfully.',
			tuners: [
				{
					index: 0,
					in_use: false,
					channel_number: null,
					channel_name: null,
					target_ip: null,
					client: null,
					warning: null,
					signal_strength_percent: null,
					signal_quality_percent: null,
					symbol_quality_percent: null,
					network_rate_bps: null,
				},
			],
		});

		render(Page);

		const popover = await screen.findByRole('tooltip');
		const terminateBtn = within(popover).getByText('Terminate');
		await fireEvent.click(terminateBtn);

		const modal = screen.getByRole('dialog');
		expect(within(modal).getByText('Terminate Tuner 0 Usage?')).toBeInTheDocument();
		expect(within(modal).getByText(/Tuner 0 is streaming to external client/)).toBeInTheDocument();

		const confirmBtn = within(modal).getByText('Terminate Stream');
		await fireEvent.click(confirmBtn);

		expect(terminateTuner).toHaveBeenCalledWith(0);
	});

	it('renders server badges and filters recordings and rules by server', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-builtin',
				title: 'Builtin Show',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 7200,
				record_end: nowSeconds() - 3600,
				is_dvr_file: true,
				provider: 'builtin',
			},
			{
				recording_id: 'rec-hdhr',
				title: 'HDHR Show',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 7200,
				record_end: nowSeconds() - 3600,
				is_dvr_file: true,
				provider: 'hdhomerun',
			},
		]);
		listRecordingRules.mockResolvedValue([
			{
				RecordingRuleID: 'rule-builtin',
				SeriesID: 's1',
				Title: 'Builtin Rule',
				provider: 'builtin',
			},
			{
				RecordingRuleID: 'rule-hdhr',
				SeriesID: 's2',
				Title: 'HDHR Rule',
				provider: 'hdhomerun',
			},
		]);

		render(Page);

		expect(await screen.findByText('Builtin Show')).toBeInTheDocument();
		expect(screen.getByText('HDHR Show')).toBeInTheDocument();
		expect(screen.getByText('Builtin Rule')).toBeInTheDocument();
		expect(screen.getByText('HDHR Rule')).toBeInTheDocument();

		// Filter by Built-in DVR
		const builtinChip = screen.getByRole('button', { name: 'Built-in DVR' });
		await fireEvent.click(builtinChip);

		expect(screen.getByText('Builtin Show')).toBeInTheDocument();
		expect(screen.queryByText('HDHR Show')).not.toBeInTheDocument();
		expect(screen.getByText('Builtin Rule')).toBeInTheDocument();
		expect(screen.queryByText('HDHR Rule')).not.toBeInTheDocument();

		// Filter by HDHomeRun DVR
		const hdhrChip = screen.getByRole('button', { name: 'HDHomeRun DVR' });
		await fireEvent.click(hdhrChip);

		expect(screen.queryByText('Builtin Show')).not.toBeInTheDocument();
		expect(screen.getByText('HDHR Show')).toBeInTheDocument();
		expect(screen.queryByText('Builtin Rule')).not.toBeInTheDocument();
		expect(screen.getByText('HDHR Rule')).toBeInTheDocument();
	});

	it('allows recording a program when watching live TV from an in-progress recording', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-in-prog',
				title: 'Live News',
				channel_name: 'KDFW',
				channel_number: '4.1',
				start: nowSeconds() - 600,
				record_end: nowSeconds() + 1200,
				is_dvr_file: false,
			},
		]);
		addHDHomeRunRecordingRule.mockResolvedValue([]);

		render(Page);

		const watchLiveBtn = await screen.findByRole('button', { name: /Watch Live/i });
		await fireEvent.click(watchLiveBtn);

		const playerDialog = await screen.findByRole('dialog', { name: '4.1 KDFW' });
		expect(playerDialog).toBeInTheDocument();

		const recordBtn = within(playerDialog).getByRole('button', { name: /Record/i });
		await fireEvent.click(recordBtn);

		const episodeBtn = within(playerDialog).getByRole('button', { name: /Record Episode/i });
		await fireEvent.click(episodeBtn);

		expect(addHDHomeRunRecordingRule).toHaveBeenCalledWith(
			expect.objectContaining({
				channel: '4.1',
			}),
		);
	});

	it('renders rich metadata badges (resolution, captions, audio, duration, synopsis, file size)', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-rich',
				title: 'Planet Earth',
				episode_title: 'Mountains',
				synopsis: 'A journey through highest mountain ranges.',
				channel_name: 'BBC America',
				channel_number: '11.1',
				start: nowSeconds() - 3600,
				record_end: nowSeconds() - 1800,
				duration_seconds: 1800,
				file_size_bytes: 1_500_000_000,
				has_captions: true,
				video_width: 1920,
				video_height: 1080,
				audio_codec: 'ac3',
				audio_channels: 6,
				category: 'Documentary',
				image_url: 'http://example.com/earth.jpg',
				is_dvr_file: true,
				provider: 'builtin',
			},
		]);

		render(Page);

		expect(await screen.findByText('Planet Earth')).toBeInTheDocument();
		expect(screen.getByText('Mountains')).toBeInTheDocument();
		expect(screen.getByText('A journey through highest mountain ranges.')).toBeInTheDocument();
		expect(screen.getByText('1080p')).toBeInTheDocument();
		expect(screen.getByText('CC')).toBeInTheDocument();
		expect(screen.getByText('5.1')).toBeInTheDocument();
		expect(screen.getByText('30m')).toBeInTheDocument();
		expect(screen.getByText('1.5 GB')).toBeInTheDocument();
		expect(screen.getByText('Documentary')).toBeInTheDocument();
	});

	it('falls back to placeholder icon when recording image fails to load', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-broken-img',
				title: 'Broken Image Show',
				channel_name: 'NBC',
				channel_number: '4.1',
				start: nowSeconds() - 3600,
				record_end: nowSeconds() - 1800,
				image_url: 'http://localhost:5273/api/dvr/recordings/rec-broken-img/poster.jpg',
				provider: 'builtin',
			},
		]);

		const { container } = render(Page);

		expect(await screen.findByText('Broken Image Show')).toBeInTheDocument();
		const img = container.querySelector('img.rec-thumb');
		expect(img).not.toBeNull();
		expect(img).toHaveAttribute('src', 'http://localhost:5273/api/dvr/recordings/rec-broken-img/poster.jpg');

		await fireEvent.error(img!);

		expect(container.querySelector('img.rec-thumb')).toBeNull();
		expect(screen.getByText('📺')).toBeInTheDocument();
	});

	it('splits recorded programs into Shows, Movies, and Sports sections', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-show-1',
				title: 'Cheers',
				episode_title: 'Sammy',
				start: nowSeconds() - 3600,
				record_end: nowSeconds() - 1800,
				category: 'Comedy',
				provider: 'builtin',
			},
			{
				recording_id: 'rec-movie-1',
				title: 'The Matrix',
				start: nowSeconds() - 7200,
				record_end: nowSeconds() - 3600,
				category: 'Movie',
				provider: 'builtin',
			},
			{
				recording_id: 'rec-sport-1',
				title: 'NFL Football',
				episode_title: 'Dallas Cowboys at Arizona Cardinals',
				start: nowSeconds() - 10800,
				record_end: nowSeconds() - 7200,
				provider: 'builtin',
			},
		]);

		render(Page);

		expect((await screen.findAllByText(/Shows \(1\)/i)).length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText(/Movies \(1\)/i).length).toBeGreaterThanOrEqual(1);
		expect(screen.getAllByText(/Sports \(1\)/i).length).toBeGreaterThanOrEqual(1);

		expect(screen.getByText('Cheers')).toBeInTheDocument();
		expect(screen.getByText('The Matrix')).toBeInTheDocument();
		expect(screen.getByText('NFL Football')).toBeInTheDocument();

		// Check sport-specific placeholder icon
		expect(screen.getByText('🏈')).toBeInTheDocument();
	});

	it('filters recordings by category when clicking category filter chips', async () => {
		listRecordings.mockResolvedValue([
			{
				recording_id: 'rec-show-1',
				title: 'Cheers',
				start: nowSeconds() - 3600,
				record_end: nowSeconds() - 1800,
				provider: 'builtin',
			},
			{
				recording_id: 'rec-sport-1',
				title: 'NFL Football',
				episode_title: 'Dallas Cowboys at Arizona Cardinals',
				start: nowSeconds() - 7200,
				record_end: nowSeconds() - 3600,
				provider: 'builtin',
			},
		]);

		render(Page);

		expect(await screen.findByText('Cheers')).toBeInTheDocument();
		expect(screen.getByText('NFL Football')).toBeInTheDocument();

		// Click Sports filter chip
		const sportsChip = screen.getByRole('button', { name: /Sports/i });
		await fireEvent.click(sportsChip);

		expect(screen.queryByText('Cheers')).not.toBeInTheDocument();
		expect(screen.getByText('NFL Football')).toBeInTheDocument();
	});
});

