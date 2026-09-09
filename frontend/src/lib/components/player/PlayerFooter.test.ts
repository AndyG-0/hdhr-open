import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE_URL: 'http://api.test' },
}));

import PlayerFooter from './PlayerFooter.svelte';

describe('PlayerFooter.svelte', () => {
	const defaultProps = {
		displayedPosition: 50,
		duration: 100,
		seekable: true,
		paused: false,
		volume: 1,
		muted: false,
		onSeek: vi.fn(),
		onTogglePlay: vi.fn(),
		onRewind: vi.fn(),
		onFastForward: vi.fn(),
		onVolumeChange: vi.fn(),
		onMuteToggle: vi.fn(),
		onToggleFullscreen: vi.fn(),
		onToggleCaptions: vi.fn(),
		onSelectAudioTrack: vi.fn(),
		onSelectCaptionTrack: vi.fn(),
		onPlaybackRateChange: vi.fn(),
		onAspectRatioChange: vi.fn(),
		onTogglePlaybackInfo: vi.fn(),
	};

	it('renders pause button when playing and triggers onTogglePlay on click', async () => {
		const onTogglePlay = vi.fn();
		render(PlayerFooter, {
			props: {
				...defaultProps,
				paused: false,
				onTogglePlay,
			},
		});

		const playBtn = screen.getByRole('button', { name: /Pause/i });
		expect(playBtn).toBeInTheDocument();

		await fireEvent.click(playBtn);
		expect(onTogglePlay).toHaveBeenCalled();
	});

	it('renders play button when paused', () => {
		render(PlayerFooter, {
			props: {
				...defaultProps,
				paused: true,
			},
		});

		expect(screen.getByRole('button', { name: /^Play$/ })).toBeInTheDocument();
	});

	it('calls onRewind and onFastForward when rewind and forward buttons are clicked', async () => {
		const onRewind = vi.fn();
		const onFastForward = vi.fn();
		render(PlayerFooter, {
			props: {
				...defaultProps,
				seekable: true,
				onRewind,
				onFastForward,
			},
		});

		const rewindBtn = screen.getByRole('button', { name: /Rewind/i });
		await fireEvent.click(rewindBtn);
		expect(onRewind).toHaveBeenCalled();

		const ffBtn = screen.getByRole('button', { name: /Fast Forward/i });
		await fireEvent.click(ffBtn);
		expect(onFastForward).toHaveBeenCalled();
	});

	it('renders captions button when hasCaptions is true and triggers onToggleCaptions', async () => {
		const onToggleCaptions = vi.fn();
		render(PlayerFooter, {
			props: {
				...defaultProps,
				hasCaptions: true,
				captionsEnabled: false,
				onToggleCaptions,
			},
		});

		const ccBtn = screen.getByRole('button', { name: /Subtitles|Closed Captions/i });
		expect(ccBtn).toBeInTheDocument();

		await fireEvent.click(ccBtn);
		expect(onToggleCaptions).toHaveBeenCalled();
	});

	it('renders PiP button when pipSupported is true and triggers onTogglePip', async () => {
		const onTogglePip = vi.fn();
		render(PlayerFooter, {
			props: {
				...defaultProps,
				pipSupported: true,
				onTogglePip,
			},
		});

		const pipBtn = screen.getByRole('button', { name: /Picture in Picture/i });
		expect(pipBtn).toBeInTheDocument();

		await fireEvent.click(pipBtn);
		expect(onTogglePip).toHaveBeenCalled();
	});

	it('triggers onToggleFullscreen when fullscreen button is clicked', async () => {
		const onToggleFullscreen = vi.fn();
		render(PlayerFooter, {
			props: {
				...defaultProps,
				isFullscreen: false,
				onToggleFullscreen,
			},
		});

		const fsBtn = screen.getByRole('button', { name: /Fullscreen/i });
		await fireEvent.click(fsBtn);
		expect(onToggleFullscreen).toHaveBeenCalled();
	});
});
