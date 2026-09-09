import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import MiniPlayer from './MiniPlayer.svelte';

describe('MiniPlayer.svelte', () => {
	it('renders title and subtitle', () => {
		render(MiniPlayer, {
			props: {
				title: 'Morning Show',
				subtitle: 'Episode 4',
				paused: false,
				onTogglePlay: vi.fn(),
				onClose: vi.fn(),
				onExpand: vi.fn(),
			},
		});

		expect(screen.getByText('Morning Show')).toBeInTheDocument();
		expect(screen.getByText('Episode 4')).toBeInTheDocument();
	});

	it('calls onExpand when clicking the bar or pressing Enter', async () => {
		const onExpand = vi.fn();
		render(MiniPlayer, {
			props: {
				title: 'Morning Show',
				paused: false,
				onTogglePlay: vi.fn(),
				onClose: vi.fn(),
				onExpand,
			},
		});

		const expandBtn = screen.getByRole('button', { name: 'Expand player' });
		await fireEvent.click(expandBtn);
		expect(onExpand).toHaveBeenCalledTimes(1);

		const miniBar = screen.getByText('Morning Show').closest('.mini-bar')!;
		await fireEvent.keyDown(miniBar, { key: 'Enter' });
		expect(onExpand).toHaveBeenCalledTimes(2);
	});

	it('toggles play/pause and triggers onTogglePlay', async () => {
		const onTogglePlay = vi.fn();
		const { rerender } = render(MiniPlayer, {
			props: {
				title: 'Morning Show',
				paused: false,
				onTogglePlay,
				onClose: vi.fn(),
				onExpand: vi.fn(),
			},
		});

		const pauseBtn = screen.getByRole('button', { name: 'Pause' });
		await fireEvent.click(pauseBtn);
		expect(onTogglePlay).toHaveBeenCalled();

		rerender({
			title: 'Morning Show',
			paused: true,
			onTogglePlay,
			onClose: vi.fn(),
			onExpand: vi.fn(),
		});

		expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument();
	});

	it('calls onClose when close button is clicked', async () => {
		const onClose = vi.fn();
		render(MiniPlayer, {
			props: {
				title: 'Morning Show',
				paused: false,
				onTogglePlay: vi.fn(),
				onClose,
				onExpand: vi.fn(),
			},
		});

		const closeBtn = screen.getByRole('button', { name: 'Close player' });
		await fireEvent.click(closeBtn);
		expect(onClose).toHaveBeenCalled();
	});
});
