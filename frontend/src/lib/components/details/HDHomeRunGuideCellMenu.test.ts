import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import HDHomeRunGuideCellMenu from './HDHomeRunGuideCellMenu.svelte';
import type { HDHomeRunGuideEntry } from '$lib/api';

describe('HDHomeRunGuideCellMenu.svelte', () => {
	const mockAiring: HDHomeRunGuideEntry = {
		title: 'Evening Show',
		episode_title: 'Special Report',
		season_number: 2,
		episode_number: '5',
		synopsis: 'Tonight in-depth report',
		start: Math.floor(Date.now() / 1000) - 300,
		end: Math.floor(Date.now() / 1000) + 1500,
		is_new: true,
		is_hd: true,
	};

	const defaultProps = {
		airing: mockAiring,
		channelName: 'KDFW',
		channelNumber: '4.1',
		x: 100,
		y: 150,
		existingRule: null,
		loading: false,
		pending: false,
		onRecordEpisode: vi.fn(),
		onRecordSeries: vi.fn(),
		onOpenOptions: vi.fn(),
		onCancelRule: vi.fn(),
		onClose: vi.fn(),
	};

	it('renders airing title, episode header, and channel badge', () => {
		render(HDHomeRunGuideCellMenu, { props: defaultProps });

		expect(screen.getByText('Evening Show')).toBeInTheDocument();
		expect(screen.getByText(/S2E5 • Special Report/i)).toBeInTheDocument();
		expect(screen.getByText('4.1')).toBeInTheDocument();
		expect(screen.getByText('KDFW')).toBeInTheDocument();
	});

	it('renders Record Episode and Record Series buttons when no rule exists and triggers callbacks', async () => {
		const onRecordEpisode = vi.fn();
		const onRecordSeries = vi.fn();
		render(HDHomeRunGuideCellMenu, {
			props: {
				...defaultProps,
				onRecordEpisode,
				onRecordSeries,
			},
		});

		const recordEpBtn = screen.getByRole('menuitem', { name: /Record Episode/i });
		await fireEvent.click(recordEpBtn);
		expect(onRecordEpisode).toHaveBeenCalled();

		const recordSeriesBtn = screen.getByRole('menuitem', { name: /Record Series/i });
		await fireEvent.click(recordSeriesBtn);
		expect(onRecordSeries).toHaveBeenCalled();
	});

	it('renders Cancel Recording button when rule exists and calls onCancelRule with ruleId', async () => {
		const onCancelRule = vi.fn();
		render(HDHomeRunGuideCellMenu, {
			props: {
				...defaultProps,
				existingRule: {
					RecordingRuleID: 'rule-xyz',
					SeriesID: 'series-1',
					Title: 'Evening Show',
				},
				onCancelRule,
			},
		});

		const cancelBtn = screen.getByRole('menuitem', { name: /Cancel Recording/i });
		await fireEvent.click(cancelBtn);

		expect(onCancelRule).toHaveBeenCalledWith('rule-xyz');
	});

	it('renders Watch button for live airing and triggers onWatch', async () => {
		const onWatch = vi.fn();
		render(HDHomeRunGuideCellMenu, {
			props: {
				...defaultProps,
				onWatch,
			},
		});

		const watchBtn = screen.getByRole('menuitem', { name: /Watch/i });
		await fireEvent.click(watchBtn);

		expect(onWatch).toHaveBeenCalled();
	});

	it('calls onClose when Escape key is pressed', async () => {
		const onClose = vi.fn();
		render(HDHomeRunGuideCellMenu, {
			props: {
				...defaultProps,
				onClose,
			},
		});

		await fireEvent.keyDown(window, { key: 'Escape' });
		expect(onClose).toHaveBeenCalled();
	});
});
