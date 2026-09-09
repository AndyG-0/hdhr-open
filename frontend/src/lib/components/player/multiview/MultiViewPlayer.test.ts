import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import MultiViewPlayer from './MultiViewPlayer.svelte';
import { closeAll, addFeed, initTunerCapacity } from '$lib/stores/multiview';

vi.mock('$lib/mpegts-player', () => ({
	createMpegtsPlayer: () => ({
		createPlayerAt: vi.fn(),
		teardownPlayer: vi.fn(),
		fetchServerDetail: vi.fn(),
	}),
}));

const {
	startWatch,
	heartbeatWatch,
	stopWatch,
	getTunerStatus,
	getTunerInfo,
	hdhomerunPlaybackUrl,
	hdhomerunRecordingStreamUrl,
	getHDHomeRunChannels,
	getNetworkIntegration,
} = vi.hoisted(() => ({
	startWatch: vi.fn().mockResolvedValue({ recording_id: 'rec1', session_id: 'sess1' }),
	heartbeatWatch: vi.fn().mockResolvedValue(undefined),
	stopWatch: vi.fn(),
	getTunerStatus: vi.fn().mockResolvedValue([]),
	getTunerInfo: vi.fn().mockResolvedValue({ friendly_name: 'HDHomeRun CONNECT', tuner_count: 2 }),
	hdhomerunPlaybackUrl: vi.fn((url: string) => `http://localhost:8000${url}`),
	hdhomerunRecordingStreamUrl: vi.fn((url: string) => `http://localhost:8000/api/dvr/recording-stream?url=${encodeURIComponent(url)}`),
	getHDHomeRunChannels: vi.fn().mockResolvedValue({ channels: [] }),
	getNetworkIntegration: vi.fn().mockResolvedValue({ settings: { favorite_channels: [] } }),
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
		getHDHomeRunChannels,
		getNetworkIntegration,
	},
}));

const mockChannels = [
	{
		channel_number: '2.1',
		name: 'FOX 4',
		is_hd: true,
		is_drm: false,
		stream_url: '',
		playback_url: '/auto/v2.1',
		now: {
			title: 'Good Day',
			episode_title: null,
			start: 1000,
			end: 2000,
			series_id: null,
			channel_number: '2.1',
		},
		next: null,
	},
	{
		channel_number: '4.1',
		name: 'NBC 5',
		is_hd: true,
		is_drm: false,
		stream_url: '',
		playback_url: '/auto/v4.1',
		now: {
			title: 'Today Show',
			episode_title: null,
			start: 1000,
			end: 2000,
			series_id: null,
			channel_number: '4.1',
		},
		next: null,
	},
];

describe('MultiViewPlayer', () => {
	beforeEach(() => {
		closeAll();
		vi.clearAllMocks();
		getTunerInfo.mockResolvedValue({ friendly_name: 'HDHomeRun CONNECT', tuner_count: 2 });
		getTunerStatus.mockResolvedValue([]);
	});

	it('renders toolbar, 2-tuner active feed count, and slot tiles, hiding 3-Up and Quad buttons on 2 tuners', async () => {
		await addFeed(mockChannels[0]);
		await addFeed(mockChannels[1]);

		render(MultiViewPlayer, {
			props: {
				channels: mockChannels,
				favoriteChannels: new Set(['2.1']),
				onClose: vi.fn(),
			},
		});

		expect(screen.getByText('Multi-View Playback')).toBeInTheDocument();
		expect(screen.getByText('2 of 2 Feeds Active')).toBeInTheDocument();
		expect(screen.getByText('2.1')).toBeInTheDocument();
		expect(screen.getByText('4.1')).toBeInTheDocument();
		expect(screen.getByText('FOX 4')).toBeInTheDocument();
		expect(screen.getByText('NBC 5')).toBeInTheDocument();

		// 2-Up is present, 3-Up and Quad are hidden
		expect(screen.getByRole('button', { name: '2-Up Split' })).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: '3-Up Hero' })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Quad Grid' })).not.toBeInTheDocument();
	});

	it('switches layout when clicking layout buttons on a 4-tuner setup', async () => {
		getTunerInfo.mockResolvedValue({ friendly_name: 'HDHomeRun FLEX 4K', tuner_count: 4 });
		await initTunerCapacity();

		await addFeed(mockChannels[0]);
		await addFeed(mockChannels[1]);

		render(MultiViewPlayer, {
			props: {
				channels: mockChannels,
				onClose: vi.fn(),
			},
		});

		expect(screen.getByText('2 of 4 Feeds Active')).toBeInTheDocument();

		const quadBtn = screen.getByRole('button', { name: 'Quad Grid' });
		await fireEvent.click(quadBtn);

		expect(screen.getAllByText('Add Feed').length).toBeGreaterThan(0);
	});
});

