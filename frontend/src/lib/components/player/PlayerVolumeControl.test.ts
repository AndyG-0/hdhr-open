import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import PlayerVolumeControl from './PlayerVolumeControl.svelte';

describe('PlayerVolumeControl.svelte', () => {
	it('renders mute button when unmuted and calls onMuteToggle on click', async () => {
		const onMuteToggle = vi.fn();
		render(PlayerVolumeControl, {
			props: {
				volume: 0.8,
				muted: false,
				onVolumeChange: vi.fn(),
				onMuteToggle,
			},
		});

		const muteBtn = screen.getByRole('button', { name: 'Mute' });
		expect(muteBtn).toBeInTheDocument();

		await fireEvent.click(muteBtn);
		expect(onMuteToggle).toHaveBeenCalled();
	});

	it('renders unmute button when muted', () => {
		render(PlayerVolumeControl, {
			props: {
				volume: 0.8,
				muted: true,
				onVolumeChange: vi.fn(),
				onMuteToggle: vi.fn(),
			},
		});

		expect(screen.getByRole('button', { name: 'Unmute' })).toBeInTheDocument();
	});

	it('adjusts volume with keyboard arrow keys', async () => {
		const onVolumeChange = vi.fn();
		render(PlayerVolumeControl, {
			props: {
				volume: 0.5,
				muted: false,
				onVolumeChange,
				onMuteToggle: vi.fn(),
			},
		});

		const slider = screen.getByLabelText('Volume');

		await fireEvent.keyDown(slider, { key: 'ArrowUp' });
		expect(onVolumeChange).toHaveBeenCalledWith(0.55);

		await fireEvent.keyDown(slider, { key: 'ArrowDown' });
		expect(onVolumeChange).toHaveBeenCalledWith(0.45);
	});

	it('clamps volume adjustments at bounds 0 and 1', async () => {
		const onVolumeChange = vi.fn();
		render(PlayerVolumeControl, {
			props: {
				volume: 0.98,
				muted: false,
				onVolumeChange,
				onMuteToggle: vi.fn(),
			},
		});

		const slider = screen.getByLabelText('Volume');
		await fireEvent.keyDown(slider, { key: 'ArrowRight' });
		expect(onVolumeChange).toHaveBeenCalledWith(1);
	});
});
