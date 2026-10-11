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
	is_drm: false,
	hidden_is_manual: false,
	affiliate: null,
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
		await waitFor(() => expect(onStationsChanged).toHaveBeenCalledWith([{ station_id: 's1', name: 'Station 1' }]));
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

		await waitFor(() =>
			expect(updateChannelSetting).toHaveBeenCalledWith('c1', expect.objectContaining({ guide_provider: null })),
		);
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

	it('filters channels by mapped/unmapped status', async () => {
		const mappedChannel = { ...channel, id: 'c1', name: 'Channel Five', xmltv_channel_id: 'wnbc.us' };
		const unmappedChannel = { ...channel, id: 'c2', name: 'Channel Six', xmltv_channel_id: '' };
		getChannelSettings.mockResolvedValue([mappedChannel, unmappedChannel]);

		render(ChannelLineupSection, {
			xmltvFeedChannels: [],
			sdStations: [],
			onFeedChannelsChanged: vi.fn(),
			onStationsChanged: vi.fn(),
		});
		await screen.findByText('Channel Five');
		expect(screen.getByText('Channel Six')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: /^Mapped/ }));
		expect(screen.getByText('Channel Five')).toBeInTheDocument();
		expect(screen.queryByText('Channel Six')).not.toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: /^Unmapped/ }));
		expect(screen.queryByText('Channel Five')).not.toBeInTheDocument();
		expect(screen.getByText('Channel Six')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: /^All/ }));
		expect(screen.getByText('Channel Five')).toBeInTheDocument();
		expect(screen.getByText('Channel Six')).toBeInTheDocument();
	});

	it('shows a restricted badge and auto-hidden hint for a DRM channel', async () => {
		const drmChannel = { ...channel, is_drm: true, hidden: true, hidden_is_manual: false };
		getChannelSettings.mockResolvedValue([drmChannel]);

		render(ChannelLineupSection, {
			xmltvFeedChannels: [],
			sdStations: [],
			onFeedChannelsChanged: vi.fn(),
			onStationsChanged: vi.fn(),
		});

		expect(await screen.findByText('Restricted')).toBeInTheDocument();
		expect(
			screen.getByText(
				"Automatically hidden — the broadcaster has applied usage restrictions, so this channel usually can't be played through this tuner.",
			),
		).toBeInTheDocument();
		expect(screen.getByRole('checkbox', { name: 'Hidden from guide' })).toBeChecked();
	});

	it('shows the affiliate badge when the tuner lineup reports one', async () => {
		const affiliateChannel = { ...channel, affiliate: 'CBS' };
		getChannelSettings.mockResolvedValue([affiliateChannel]);

		render(ChannelLineupSection, {
			xmltvFeedChannels: [],
			sdStations: [],
			onFeedChannelsChanged: vi.fn(),
			onStationsChanged: vi.fn(),
		});

		expect(await screen.findByText('Channel Five')).toBeInTheDocument();
		expect(screen.getByText('CBS')).toBeInTheDocument();
	});

	it('toggling the hidden checkbox and saving persists the override', async () => {
		render(ChannelLineupSection, {
			xmltvFeedChannels: [],
			sdStations: [],
			onFeedChannelsChanged: vi.fn(),
			onStationsChanged: vi.fn(),
		});
		await screen.findByText('Channel Five');

		const checkbox = screen.getByRole('checkbox', { name: 'Hidden from guide' });
		expect(checkbox).not.toBeChecked();
		await fireEvent.click(checkbox);
		expect(checkbox).toBeChecked();

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() =>
			expect(updateChannelSetting).toHaveBeenCalledWith('c1', expect.objectContaining({ hidden: true })),
		);
	});
});
