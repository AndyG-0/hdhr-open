import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { getXmltvStats, updateNetworkIntegration, getXmltvFeedChannels, reloadXmltvGuide } = vi.hoisted(() => ({
	getXmltvStats: vi.fn(),
	updateNetworkIntegration: vi.fn(),
	getXmltvFeedChannels: vi.fn(),
	reloadXmltvGuide: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { getXmltvStats, updateNetworkIntegration, getXmltvFeedChannels, reloadXmltvGuide },
}));

import XmltvFeedSection from './XmltvFeedSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	getXmltvStats.mockResolvedValue({
		last_refreshed_at: null,
		channels_in_feed: 0,
		mapped_channels_count: 0,
		days_count: 0,
		start_date: null,
		end_date: null,
		programs_count: 0,
	});
	updateNetworkIntegration.mockResolvedValue({ settings: {} });
	getXmltvFeedChannels.mockResolvedValue([]);
});

describe('XmltvFeedSection', () => {
	it('seeds the URL input from initialUrl and loads stats', async () => {
		getXmltvStats.mockResolvedValue({
			last_refreshed_at: '2026-01-01T00:00:00Z',
			channels_in_feed: 5,
			mapped_channels_count: 3,
			days_count: 7,
			start_date: '2026-01-01',
			end_date: '2026-01-08',
			programs_count: 1200,
		});
		render(XmltvFeedSection, {
			initialUrl: 'http://example.com/guide.xml',
			onFeedChannelsChanged: vi.fn(),
		});

		await waitFor(() =>
			expect(screen.getByPlaceholderText('http://example.com/guide.xml')).toHaveValue(
				'http://example.com/guide.xml',
			),
		);
		expect(await screen.findByText('1,200')).toBeInTheDocument();
	});

	it('saves the URL and notifies onFeedChannelsChanged', async () => {
		const onFeedChannelsChanged = vi.fn();
		getXmltvFeedChannels.mockResolvedValue([{ xmltv_channel_id: 'ch1', display_names: ['Channel 1'] }]);
		render(XmltvFeedSection, { initialUrl: '', onFeedChannelsChanged });

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() => expect(updateNetworkIntegration).toHaveBeenCalledWith('xmltv', { url: '' }));
		await waitFor(() => expect(onFeedChannelsChanged).toHaveBeenCalledWith([
			{ xmltv_channel_id: 'ch1', display_names: ['Channel 1'] },
		]));
	});

	it('shows an error message when saving fails', async () => {
		updateNetworkIntegration.mockRejectedValue(new Error('boom'));
		render(XmltvFeedSection, { initialUrl: '', onFeedChannelsChanged: vi.fn() });

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		expect(await screen.findByText('Could not save these settings.')).toBeInTheDocument();
	});

	it('reloads the guide and notifies onFeedChannelsChanged', async () => {
		const onFeedChannelsChanged = vi.fn();
		getXmltvFeedChannels.mockResolvedValue([]);
		reloadXmltvGuide.mockResolvedValue({
			ok: true,
			message: 'ok',
			stats: {
				last_refreshed_at: '2026-01-01T00:00:00Z',
				channels_in_feed: 1,
				mapped_channels_count: 1,
				days_count: 1,
				start_date: '2026-01-01',
				end_date: '2026-01-02',
				programs_count: 10,
			},
		});
		render(XmltvFeedSection, { initialUrl: 'http://example.com/guide.xml', onFeedChannelsChanged });
		await waitFor(() => expect(screen.getByPlaceholderText('http://example.com/guide.xml')).toHaveValue('http://example.com/guide.xml'));

		await fireEvent.click(screen.getByRole('button', { name: 'Reload Feed' }));

		await waitFor(() => expect(reloadXmltvGuide).toHaveBeenCalled());
		expect(onFeedChannelsChanged).toHaveBeenCalled();
	});
});
