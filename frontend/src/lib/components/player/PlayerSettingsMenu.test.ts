import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE_URL: 'http://api.test' },
}));

import PlayerSettingsMenu from './PlayerSettingsMenu.svelte';
import { keepPlayingOnNavigate } from '$lib/stores/playback';
import { get } from 'svelte/store';

describe('PlayerSettingsMenu.svelte', () => {
	const defaultProps = {
		showMenu: true,
		playbackRate: 1.0,
		aspectRatio: 'contain' as const,
		seekable: true,
		onPlaybackRateChange: vi.fn(),
		onAspectRatioChange: vi.fn(),
		onSelectAudioTrack: vi.fn(),
		onSelectCaptionTrack: vi.fn(),
		onToggleCaptions: vi.fn(),
		onTogglePlaybackInfo: vi.fn(),
		onClose: vi.fn(),
	};

	it('renders main settings menu items when showMenu is true', () => {
		render(PlayerSettingsMenu, { props: defaultProps });

		expect(screen.getByText(/Playback Settings/i)).toBeInTheDocument();
		expect(screen.getByText(/Aspect Ratio/i)).toBeInTheDocument();
		expect(screen.getByText(/Speed/i)).toBeInTheDocument();
		expect(screen.getByText(/Keep playing when I navigate away/i)).toBeInTheDocument();
	});

	it('navigates into Speed submenu and selects a new playback speed', async () => {
		const onPlaybackRateChange = vi.fn();
		render(PlayerSettingsMenu, {
			props: {
				...defaultProps,
				onPlaybackRateChange,
			},
		});

		const speedNavBtn = screen.getByRole('button', { name: /Speed/i });
		await fireEvent.click(speedNavBtn);

		const speed15Btn = screen.getByRole('button', { name: '1.5x' });
		await fireEvent.click(speed15Btn);

		expect(onPlaybackRateChange).toHaveBeenCalledWith(1.5);
	});

	it('navigates into Aspect Ratio submenu and selects a new ratio', async () => {
		const onAspectRatioChange = vi.fn();
		render(PlayerSettingsMenu, {
			props: {
				...defaultProps,
				onAspectRatioChange,
			},
		});

		const aspectNavBtn = screen.getByRole('button', { name: /Aspect Ratio/i });
		await fireEvent.click(aspectNavBtn);

		const stretchBtn = screen.getByRole('button', { name: 'Stretch' });
		await fireEvent.click(stretchBtn);

		expect(onAspectRatioChange).toHaveBeenCalledWith('fill');
	});

	it('toggles keepPlayingOnNavigate store on click', async () => {
		const initial = get(keepPlayingOnNavigate);
		render(PlayerSettingsMenu, { props: defaultProps });

		const toggleBtn = screen.getByRole('button', { name: /Keep playing when I navigate away/i });
		await fireEvent.click(toggleBtn);

		expect(get(keepPlayingOnNavigate)).toBe(!initial);
	});

	it('calls onTogglePlaybackInfo when info item is clicked', async () => {
		const onTogglePlaybackInfo = vi.fn();
		render(PlayerSettingsMenu, {
			props: {
				...defaultProps,
				onTogglePlaybackInfo,
			},
		});

		const infoBtn = screen.getByRole('button', { name: /Playback Info/i });
		await fireEvent.click(infoBtn);

		expect(onTogglePlaybackInfo).toHaveBeenCalled();
	});

	it('calls onClose when close button is clicked', async () => {
		const onClose = vi.fn();
		render(PlayerSettingsMenu, {
			props: {
				...defaultProps,
				onClose,
			},
		});

		const closeBtn = screen.getByRole('button', { name: '✕' });
		await fireEvent.click(closeBtn);

		expect(onClose).toHaveBeenCalled();
	});
});
