import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import HDHomeRunGuideGrid from './HDHomeRunGuideGrid.svelte';
import type { HDHomeRunChannel, HDHomeRunFullGuideChannel } from '$lib/api';

describe('HDHomeRunGuideGrid.svelte', () => {
	const mockChannel: HDHomeRunChannel = {
		channel_number: '4.1',
		name: 'KDFW',
		is_hd: true,
		is_drm: false,
		stream_url: 'http://tuner.local/stream/4.1',
		playback_url: '/api/hdhomerun/watch/4.1',
		now: {
			title: 'Morning News',
			episode_title: 'Early Edition',
			start: Math.floor(Date.now() / 1000) - 300,
			end: Math.floor(Date.now() / 1000) + 1500,
		},
		next: null,
	};

	const mockFullGuide: HDHomeRunFullGuideChannel[] = [
		{
			channel_number: '4.1',
			channel_name: 'KDFW',
			airings: [
				{
					title: 'Morning News',
					episode_title: 'Early Edition',
					synopsis: 'Local breaking news and traffic',
					start: Math.floor(Date.now() / 1000) - 300,
					end: Math.floor(Date.now() / 1000) + 1500,
				},
				{
					title: 'Daytime Talk',
					episode_title: null,
					synopsis: 'Celebrity guests and gossip',
					start: Math.floor(Date.now() / 1000) + 1500,
					end: Math.floor(Date.now() / 1000) + 3300,
				},
			],
		},
	];

	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('renders channel list and airings', () => {
		render(HDHomeRunGuideGrid, {
			props: {
				channels: [mockChannel],
				fullGuide: mockFullGuide,
				recordingRules: [],
				pendingRuleIds: new Set<string>(),
				favoriteChannels: new Set<string>(),
				savingFavorite: false,
				recordingLoading: null,
				officialDvrActive: false,
				onWatch: vi.fn(),
				onRecordEpisode: vi.fn(),
				onRecordSeries: vi.fn(),
				onCancelRule: vi.fn(),
				onToggleFavorite: vi.fn(),
			},
		});

		expect(screen.getByText('4.1')).toBeInTheDocument();
		expect(screen.getByText('KDFW')).toBeInTheDocument();
		expect(screen.getByText('Morning News')).toBeInTheDocument();
	});

	it('toggles channel favorite on star click', async () => {
		const onToggleFavorite = vi.fn();
		render(HDHomeRunGuideGrid, {
			props: {
				channels: [mockChannel],
				fullGuide: mockFullGuide,
				recordingRules: [],
				pendingRuleIds: new Set<string>(),
				favoriteChannels: new Set<string>(),
				savingFavorite: false,
				recordingLoading: null,
				officialDvrActive: false,
				onWatch: vi.fn(),
				onRecordEpisode: vi.fn(),
				onRecordSeries: vi.fn(),
				onCancelRule: vi.fn(),
				onToggleFavorite,
			},
		});

		const favBtn = screen.getByRole('button', { name: /Add to favorites/i });
		await fireEvent.click(favBtn);

		expect(onToggleFavorite).toHaveBeenCalledWith('4.1');
	});

	it('debounces search by 150ms before showing search results panel', async () => {
		render(HDHomeRunGuideGrid, {
			props: {
				channels: [mockChannel],
				fullGuide: mockFullGuide,
				recordingRules: [],
				pendingRuleIds: new Set<string>(),
				favoriteChannels: new Set<string>(),
				savingFavorite: false,
				recordingLoading: null,
				officialDvrActive: false,
				onWatch: vi.fn(),
				onRecordEpisode: vi.fn(),
				onRecordSeries: vi.fn(),
				onCancelRule: vi.fn(),
				onToggleFavorite: vi.fn(),
			},
		});

		const searchInput = screen.getByPlaceholderText(/Search programs/i);
		await fireEvent.input(searchInput, { target: { value: 'Talk' } });

		// Immediately before debounce timer expires, search panel should not have appeared
		expect(screen.queryByText(/Celebrity guests/i)).not.toBeInTheDocument();

		// Advance timer past 150ms
		await vi.advanceTimersByTimeAsync(200);

		// Now the debounced query has updated and search panel shows the matching result synopsis
		expect(screen.getByText(/Celebrity guests and gossip/i)).toBeInTheDocument();
	});

	it('clearing the search immediately clears results', async () => {
		render(HDHomeRunGuideGrid, {
			props: {
				channels: [mockChannel],
				fullGuide: mockFullGuide,
				recordingRules: [],
				pendingRuleIds: new Set<string>(),
				favoriteChannels: new Set<string>(),
				savingFavorite: false,
				recordingLoading: null,
				officialDvrActive: false,
				onWatch: vi.fn(),
				onRecordEpisode: vi.fn(),
				onRecordSeries: vi.fn(),
				onCancelRule: vi.fn(),
				onToggleFavorite: vi.fn(),
			},
		});

		const searchInput = screen.getByPlaceholderText(/Search programs/i);
		await fireEvent.input(searchInput, { target: { value: 'Talk' } });
		await vi.advanceTimersByTimeAsync(200);
		expect(screen.getByText(/Celebrity guests and gossip/i)).toBeInTheDocument();

		// Clear search
		const clearBtn = screen.getAllByRole('button', { name: /Clear search/i })[0];
		await fireEvent.click(clearBtn);

		expect(screen.queryByText(/Celebrity guests and gossip/i)).not.toBeInTheDocument();
	});

	it('positions the now-line inside every channel row, not just the header', () => {
		const { container } = render(HDHomeRunGuideGrid, {
			props: {
				channels: [mockChannel],
				fullGuide: mockFullGuide,
				recordingRules: [],
				pendingRuleIds: new Set<string>(),
				favoriteChannels: new Set<string>(),
				savingFavorite: false,
				recordingLoading: null,
				officialDvrActive: false,
				onWatch: vi.fn(),
				onRecordEpisode: vi.fn(),
				onRecordSeries: vi.fn(),
				onCancelRule: vi.fn(),
				onToggleFavorite: vi.fn(),
			},
		});

		const rowNowLine = container.querySelector('.channel-track .now-line');
		expect(rowNowLine).not.toBeNull();
		expect(rowNowLine?.getAttribute('style')).toMatch(/left:\s*[\d.]+px/);
	});

	it('jump-to control lets the user pick a loaded day', async () => {
		render(HDHomeRunGuideGrid, {
			props: {
				channels: [mockChannel],
				fullGuide: mockFullGuide,
				recordingRules: [],
				pendingRuleIds: new Set<string>(),
				favoriteChannels: new Set<string>(),
				savingFavorite: false,
				recordingLoading: null,
				officialDvrActive: false,
				onWatch: vi.fn(),
				onRecordEpisode: vi.fn(),
				onRecordSeries: vi.fn(),
				onCancelRule: vi.fn(),
				onToggleFavorite: vi.fn(),
			},
		});

		const jumpSelect = screen.getByLabelText('Jump to') as HTMLSelectElement;
		expect(jumpSelect.options[1]?.textContent).toBe('Today');

		await fireEvent.change(jumpSelect, { target: { value: jumpSelect.options[1].value } });

		// Selecting a day is a one-shot action — the control resets to its
		// placeholder so it can fire again on the same option.
		expect(jumpSelect.value).toBe('');
	});
});
