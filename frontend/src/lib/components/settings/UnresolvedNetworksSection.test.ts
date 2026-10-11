import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const {
	getUnresolvedSportsNetworks,
	getChannelSettings,
	saveSportsNetworkMapEntry,
	saveSportsNetworkWatchLink,
	deleteSportsNetworkWatchLink,
} = vi.hoisted(() => ({
	getUnresolvedSportsNetworks: vi.fn(),
	getChannelSettings: vi.fn(),
	saveSportsNetworkMapEntry: vi.fn(),
	saveSportsNetworkWatchLink: vi.fn(),
	deleteSportsNetworkWatchLink: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: {
		getUnresolvedSportsNetworks,
		getChannelSettings,
		saveSportsNetworkMapEntry,
		saveSportsNetworkWatchLink,
		deleteSportsNetworkWatchLink,
	},
}));

import UnresolvedNetworksSection from './UnresolvedNetworksSection.svelte';

const channel = {
	id: 'c1',
	channel_number: '7.1',
	name: 'KCBS',
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
	saveSportsNetworkMapEntry.mockResolvedValue({});
	saveSportsNetworkWatchLink.mockResolvedValue({});
	deleteSportsNetworkWatchLink.mockResolvedValue(undefined);
});

describe('UnresolvedNetworksSection', () => {
	it('shows the no-channels message when nothing is unresolved', async () => {
		getUnresolvedSportsNetworks.mockResolvedValue({ unresolved_networks: [] });

		render(UnresolvedNetworksSection);

		expect(await screen.findByText('No unresolved broadcast networks.')).toBeInTheDocument();
	});

	it('explains an OTA network has no local affiliate match, with per-game detail', async () => {
		getUnresolvedSportsNetworks.mockResolvedValue({
			unresolved_networks: [
				{
					network_name: 'CBS',
					is_ota: true,
					games: [
						{ espn_event_id: 'evt_1', league: 'nfl', start_ts: 1234567890, matchup_title: 'Cowboys at Cardinals' },
					],
				},
			],
		});

		render(UnresolvedNetworksSection);

		expect(await screen.findByText('CBS')).toBeInTheDocument();
		expect(screen.getByText('Over-the-air')).toBeInTheDocument();
		expect(screen.getByText(/No local CBS affiliate was found in your channel lineup/)).toBeInTheDocument();
		expect(screen.getByText('Cowboys at Cardinals')).toBeInTheDocument();
	});

	it('shows a manual-mapping note for a non-OTA (cable/streaming) network', async () => {
		getUnresolvedSportsNetworks.mockResolvedValue({
			unresolved_networks: [
				{
					network_name: 'ESPN',
					is_ota: false,
					games: [{ espn_event_id: 'evt_2', league: 'nfl', start_ts: 1234567890, matchup_title: 'Chiefs at Raiders' }],
					watch_url: null,
					custom_watch_url: null,
				},
			],
		});

		render(UnresolvedNetworksSection);

		expect(await screen.findByText('ESPN')).toBeInTheDocument();
		expect(screen.queryByText('Over-the-air')).not.toBeInTheDocument();
		expect(
			screen.getByText(/isn't an over-the-air network, so it requires a manual channel mapping/),
		).toBeInTheDocument();
	});

	it('assigns a channel to an unresolved network', async () => {
		getUnresolvedSportsNetworks.mockResolvedValue({
			unresolved_networks: [
				{
					network_name: 'ESPN',
					is_ota: false,
					games: [{ espn_event_id: 'evt_2', league: 'nfl', start_ts: 1234567890, matchup_title: 'Chiefs at Raiders' }],
					watch_url: null,
					custom_watch_url: null,
				},
			],
		});

		render(UnresolvedNetworksSection);
		await screen.findByText('ESPN');

		await fireEvent.change(screen.getByRole('combobox'), { target: { value: 'c1' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Assign' }));

		await waitFor(() => expect(saveSportsNetworkMapEntry).toHaveBeenCalledWith('ESPN', 'c1'));
		await waitFor(() => expect(screen.queryByText('ESPN')).not.toBeInTheDocument());
	});

	it('renders a watch link for a non-OTA network that has one', async () => {
		getUnresolvedSportsNetworks.mockResolvedValue({
			unresolved_networks: [
				{
					network_name: 'ESPN',
					is_ota: false,
					games: [{ espn_event_id: 'evt_2', league: 'nfl', start_ts: 1234567890, matchup_title: 'Chiefs at Raiders' }],
					watch_url: 'https://www.espn.com/watch/',
					custom_watch_url: null,
				},
			],
		});

		render(UnresolvedNetworksSection);

		const link = await screen.findByRole('link', { name: 'Watch ↗' });
		expect(link).toHaveAttribute('href', 'https://www.espn.com/watch/');
		expect(link).toHaveAttribute('target', '_blank');
	});

	it('does not render a watch link for a non-OTA network with no curated or custom link', async () => {
		getUnresolvedSportsNetworks.mockResolvedValue({
			unresolved_networks: [
				{
					network_name: 'SOME RSN',
					is_ota: false,
					games: [{ espn_event_id: 'evt_2', league: 'nfl', start_ts: 1234567890, matchup_title: 'Chiefs at Raiders' }],
					watch_url: null,
					custom_watch_url: null,
				},
			],
		});

		render(UnresolvedNetworksSection);
		await screen.findByText('SOME RSN');

		expect(screen.queryByRole('link', { name: 'Watch ↗' })).not.toBeInTheDocument();
	});

	it('saves a custom watch link for a non-OTA network', async () => {
		getUnresolvedSportsNetworks.mockResolvedValue({
			unresolved_networks: [
				{
					network_name: 'TNT',
					is_ota: false,
					games: [{ espn_event_id: 'evt_2', league: 'nba', start_ts: 1234567890, matchup_title: 'Lakers at Celtics' }],
					watch_url: null,
					custom_watch_url: null,
				},
			],
		});

		render(UnresolvedNetworksSection);
		await screen.findByText('TNT');

		const input = screen.getByPlaceholderText('Custom watch link (e.g. https://example.com/watch)');
		await fireEvent.input(input, { target: { value: 'https://example.com/tnt' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save link' }));

		await waitFor(() => expect(saveSportsNetworkWatchLink).toHaveBeenCalledWith('TNT', 'https://example.com/tnt'));
	});

	it('clears a custom watch link for a non-OTA network', async () => {
		getUnresolvedSportsNetworks.mockResolvedValue({
			unresolved_networks: [
				{
					network_name: 'TNT',
					is_ota: false,
					games: [{ espn_event_id: 'evt_2', league: 'nba', start_ts: 1234567890, matchup_title: 'Lakers at Celtics' }],
					watch_url: 'https://example.com/tnt',
					custom_watch_url: 'https://example.com/tnt',
				},
			],
		});

		render(UnresolvedNetworksSection);
		await screen.findByText('TNT');

		const input = screen.getByPlaceholderText('Custom watch link (e.g. https://example.com/watch)');
		expect(input).toHaveValue('https://example.com/tnt');

		await fireEvent.input(input, { target: { value: '' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save link' }));

		await waitFor(() => expect(deleteSportsNetworkWatchLink).toHaveBeenCalledWith('TNT'));
	});
});
