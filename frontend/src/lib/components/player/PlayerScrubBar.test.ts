import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import PlayerScrubBar from './PlayerScrubBar.svelte';

describe('PlayerScrubBar.svelte', () => {
	it('renders current time and remaining time formatted correctly', () => {
		render(PlayerScrubBar, {
			props: {
				displayedPosition: 65,
				duration: 180,
				onSeek: vi.fn(),
			},
		});

		expect(screen.getByText('1:05')).toBeInTheDocument();
		expect(screen.getByText('-1:55')).toBeInTheDocument();
	});

	it('toggles between remaining time and total duration when clicked', async () => {
		render(PlayerScrubBar, {
			props: {
				displayedPosition: 60,
				duration: 180,
				onSeek: vi.fn(),
			},
		});

		const rightTimeBtn = screen.getByRole('button', { name: 'Toggle time format' });
		expect(rightTimeBtn).toHaveTextContent('-2:00');

		await fireEvent.click(rightTimeBtn);
		expect(rightTimeBtn).toHaveTextContent('3:00');
	});

	it('displays recording in progress label when isInProgress is true', () => {
		render(PlayerScrubBar, {
			props: {
				displayedPosition: 60,
				duration: 180,
				isInProgress: true,
				onSeek: vi.fn(),
			},
		});

		expect(screen.getByText(/Recording/i)).toBeInTheDocument();
	});

	it('seeks with ArrowLeft and ArrowRight keys', async () => {
		const onSeek = vi.fn();
		render(PlayerScrubBar, {
			props: {
				displayedPosition: 50,
				duration: 100,
				onSeek,
			},
		});

		const slider = screen.getByRole('slider');
		await fireEvent.keyDown(slider, { key: 'ArrowLeft' });
		expect(onSeek).toHaveBeenCalledWith(40);

		await fireEvent.keyDown(slider, { key: 'ArrowRight' });
		expect(onSeek).toHaveBeenCalledWith(60);
	});

	it('clamps ArrowLeft to 0 and ArrowRight to duration', async () => {
		const onSeek = vi.fn();
		render(PlayerScrubBar, {
			props: {
				displayedPosition: 5,
				duration: 100,
				onSeek,
			},
		});

		const slider = screen.getByRole('slider');
		await fireEvent.keyDown(slider, { key: 'ArrowLeft' });
		expect(onSeek).toHaveBeenCalledWith(0);

		render(PlayerScrubBar, {
			props: {
				displayedPosition: 95,
				duration: 100,
				onSeek,
			},
		});
		const sliders = screen.getAllByRole('slider');
		await fireEvent.keyDown(sliders[sliders.length - 1], { key: 'ArrowRight' });
		expect(onSeek).toHaveBeenCalledWith(100);
	});

	it('does not seek on arrow keys when seekable is false', async () => {
		const onSeek = vi.fn();
		render(PlayerScrubBar, {
			props: {
				displayedPosition: 50,
				duration: 100,
				seekable: false,
				onSeek,
			},
		});

		const slider = screen.getByRole('slider');
		await fireEvent.keyDown(slider, { key: 'ArrowLeft' });
		expect(onSeek).not.toHaveBeenCalled();
	});

	it('calculates seek position on click based on element bounds', async () => {
		const onSeek = vi.fn();
		render(PlayerScrubBar, {
			props: {
				displayedPosition: 0,
				duration: 200,
				onSeek,
			},
		});

		const slider = screen.getByRole('slider');
		vi.spyOn(slider, 'getBoundingClientRect').mockReturnValue({
			left: 100,
			top: 0,
			width: 400,
			height: 20,
			right: 500,
			bottom: 20,
			x: 100,
			y: 0,
			toJSON: () => {},
		});

		await fireEvent.click(slider, { clientX: 200 }); // (200 - 100) / 400 = 0.25 * 200 = 50
		expect(onSeek).toHaveBeenCalledWith(50);
	});
});
