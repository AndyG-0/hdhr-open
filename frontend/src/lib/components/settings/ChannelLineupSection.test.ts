import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { getChannelSettings, getXmltvFeedChannels, getSchedulesDirectStations, updateChannelSetting, refreshGuide } =
	vi.hoisted(() => ({
		getChannelSettings: vi.fn(),
		getXmltvFeedChannels: vi.fn(),
		getSchedulesDirectStations: vi.fn(),
		updateChannelSetting: vi.fn(),
		refreshGuide: vi.fn(),
	}));

vi.mock('$lib/api', () => ({
	api: { getChannelSettings, getXmltvFeedChannels, getSchedulesDirectStations, updateChannelSetting, refreshGuide },
}));

import ChannelLineupSection from './ChannelLineupSection.svelte';

const channel = {
	id: 'c1',
	channel_number: '5.1',
	name: 'Channel Five',
	is_hd: true,
	is_favorite: false,
	hidden: false,
	guide_provider: null,
	xmltv_channel_id: '',
	xmltv_display_name: '',
	sd_station_id: '',
	sd_lineup_id: '',
};

beforeEach(() => {
	vi.clearAllMocks();
	getChannelSettings.mockResolvedValue([channel]);
	getXmltvFeedChannels.mockResolvedValue([]);
	getSchedulesDirectStations.mockResolvedValue([]);
	updateChannelSetting.mockResolvedValue({ ...channel });
});

describe('ChannelLineupSection', () => {
	it('loads channel settings on mount and notifies parent of feed/station arrays', async () => {
		const onFeedChannelsChanged = vi.fn();
		const onStationsChanged = vi.fn();
		getXmltvFeedChannels.mockResolvedValue([{ xmltv_channel_id: 'ch1', display_names: ['Channel 1'] }]);
		getSchedulesDirectStations.mockResolvedValue([{ station_id: 's1', name: 'Station 1' }]);

		render(ChannelLineupSection, {
			xmltvFeedChannels: [],
			sdStations: [],
			onFeedChannelsChanged,
			onStationsChanged,
		});

		expect(await screen.findByText('Channel Five')).toBeInTheDocument();
		await waitFor(() =>
			expect(onFeedChannelsChanged).toHaveBeenCalledWith([{ xmltv_channel_id: 'ch1', display_names: ['Channel 1'] }]),
		);
		await waitFor(() =>
			expect(onStationsChanged).toHaveBeenCalledWith([{ station_id: 's1', name: 'Station 1' }]),
		);
	});

	it('saves a channel setting', async () => {
		render(ChannelLineupSection, {
			xmltvFeedChannels: [],
			sdStations: [],
			onFeedChannelsChanged: vi.fn(),
			onStationsChanged: vi.fn(),
		});
		await screen.findByText('Channel Five');

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() => expect(updateChannelSetting).toHaveBeenCalledWith('c1', expect.objectContaining({ guide_provider: null })));
		expect(await screen.findByText('Saved.')).toBeInTheDocument();
	});

	it('refreshes the guide', async () => {
		refreshGuide.mockResolvedValue({ status: 'ok', message: 'started' });
		render(ChannelLineupSection, {
			xmltvFeedChannels: [],
			sdStations: [],
			onFeedChannelsChanged: vi.fn(),
			onStationsChanged: vi.fn(),
		});
		await screen.findByText('Channel Five');

		await fireEvent.click(screen.getByRole('button', { name: 'Refresh Guide' }));

		expect(await screen.findByText('Guide refresh started.')).toBeInTheDocument();
	});
});
