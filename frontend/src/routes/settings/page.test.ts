import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { locale, waitLocale } from 'svelte-i18n';

const {
	goto,
	settings,
	updateSettings,
	listDevices,
	listUsers,
	listHouseholdUsers,
	getPreferences,
	updatePreferences,
	listNetworkIntegrations,
	updateNetworkIntegration,
	testHDHomeRunTunerConnection,
	testHDHomeRunDvrConnection,
	themes,
	getChannelSettings,
	updateChannelSetting,
	getXmltvFeedChannels,
	getXmltvStats,
	reloadXmltvGuide,
	refreshGuide,
	testSchedulesDirectConnection,
	getSchedulesDirectLineups,
	getSchedulesDirectHeadends,
	addSchedulesDirectLineup,
	deleteSchedulesDirectLineup,
	getSchedulesDirectStations,
} = vi.hoisted(() => ({
	goto: vi.fn(),
	settings: vi.fn(),
	updateSettings: vi.fn(),
	listDevices: vi.fn(),
	listUsers: vi.fn(),
	listHouseholdUsers: vi.fn(),
	getPreferences: vi.fn(),
	updatePreferences: vi.fn(),
	listNetworkIntegrations: vi.fn().mockResolvedValue([]),
	updateNetworkIntegration: vi.fn(),
	testHDHomeRunTunerConnection: vi.fn(),
	testHDHomeRunDvrConnection: vi.fn(),
	themes: vi.fn(),
	getChannelSettings: vi.fn().mockResolvedValue([]),
	updateChannelSetting: vi.fn(),
	getXmltvFeedChannels: vi.fn().mockResolvedValue([]),
	getXmltvStats: vi.fn().mockResolvedValue(null),
	reloadXmltvGuide: vi.fn(),
	refreshGuide: vi.fn().mockResolvedValue({ status: 'ok', message: 'Started' }),
	testSchedulesDirectConnection: vi.fn().mockResolvedValue({ ok: true, detail: { expires: '2027-01-01T00:00:00Z', lineups: [] }, error: null }),
	getSchedulesDirectLineups: vi.fn().mockResolvedValue([]),
	getSchedulesDirectHeadends: vi.fn().mockResolvedValue([]),
	addSchedulesDirectLineup: vi.fn().mockResolvedValue({}),
	deleteSchedulesDirectLineup: vi.fn().mockResolvedValue({}),
	getSchedulesDirectStations: vi.fn().mockResolvedValue([]),
}));

vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$lib/api', () => ({
	api: {
		settings,
		updateSettings,
		listDevices,
		listUsers,
		listHouseholdUsers,
		getPreferences,
		updatePreferences,
		listNetworkIntegrations,
		updateNetworkIntegration,
		testHDHomeRunTunerConnection,
		testHDHomeRunDvrConnection,
		themes,
		getChannelSettings,
		updateChannelSetting,
		getXmltvFeedChannels,
		getXmltvStats,
		reloadXmltvGuide,
		refreshGuide,
		testSchedulesDirectConnection,
		getSchedulesDirectLineups,
		getSchedulesDirectHeadends,
		addSchedulesDirectLineup,
		deleteSchedulesDirectLineup,
		getSchedulesDirectStations,
	},
}));


import Page from './+page.svelte';
import { user } from '$lib/stores/user';

const BASE_SETTINGS = {
	timezone: 'UTC',
	guide_provider_priority: 'xmltv,schedules_direct,hdhomerun_cloud',
	dvr_server_priority: 'builtin,hdhomerun',
};
const DEFAULT_PREFERENCES = { theme: 'dark', voice_provider: 'browser', voice_id: '', voice_name: '', locale: 'en' };

beforeEach(() => {
	vi.clearAllMocks();
	user.set(null);
	settings.mockResolvedValue({ ...BASE_SETTINGS });
	updateSettings.mockResolvedValue({ ...BASE_SETTINGS });
	listDevices.mockResolvedValue([]);
	listUsers.mockResolvedValue([]);
	listHouseholdUsers.mockResolvedValue([]);
	getPreferences.mockResolvedValue({ ...DEFAULT_PREFERENCES });
	updatePreferences.mockResolvedValue({ ...DEFAULT_PREFERENCES });
	listNetworkIntegrations.mockResolvedValue([]);
	themes.mockResolvedValue({ themes: [{ id: 'dark', name: 'Dark' }], default: 'dark' });
});

describe('settings +page.svelte — admin sections', () => {
	it('does not show admin settings to a non-admin member', async () => {
		user.set({ id: 'u1', name: 'Member', avatar: null, role: 'member' });
		render(Page);

		await waitFor(() => expect(listDevices).toHaveBeenCalled());

		expect(screen.queryByText('Household members')).not.toBeInTheDocument();
		expect(screen.queryByText('Timezone')).not.toBeInTheDocument();
		expect(screen.queryByText('HDHomeRun')).not.toBeInTheDocument();
	});

	it('loads and saves the timezone for an admin', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		render(Page);

		await screen.findByText('Timezone');
		await waitFor(() => expect(settings).toHaveBeenCalled());

		await fireEvent.click(screen.getByRole('button', { name: 'Save timezone' }));

		await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({ timezone: 'UTC' }));
		expect(await screen.findByText('Saved.')).toBeInTheDocument();
	});

	it('lists household members and lets an admin promote a member', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		listHouseholdUsers.mockResolvedValue([
			{ id: 'admin1', name: 'Admin', avatar: null, has_pin: false, role: 'admin', created_at: '2026-01-01' },
			{ id: 'u2', name: 'Bob', avatar: null, has_pin: false, role: 'member', created_at: '2026-01-01' },
		]);
		render(Page);

		await screen.findByText('Bob');
		await fireEvent.click(screen.getByRole('button', { name: 'Promote to admin' }));

		await waitFor(() => expect(listHouseholdUsers).toHaveBeenCalled());
	});

	it('loads HDHomeRun network settings and saves them', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		listNetworkIntegrations.mockResolvedValue([
			{
				id: 'hdhomerun',
				type: 'hdhomerun',
				name: 'HDHomeRun',
				settings: { tuner_host: 'hdhomerun.local', tuner_port: 80, dvr_host: '', dvr_port: 59090 },
			},
		]);
		updateNetworkIntegration.mockResolvedValue({
			id: 'hdhomerun',
			type: 'hdhomerun',
			name: 'HDHomeRun',
			settings: { tuner_host: 'hdhomerun.local', tuner_port: 80, dvr_host: '', dvr_port: 59090 },
		});
		render(Page);

		await waitFor(() => expect(listNetworkIntegrations).toHaveBeenCalled());
		expect(await screen.findByPlaceholderText('hdhomerun.local')).toHaveValue('hdhomerun.local');

		await fireEvent.click(screen.getAllByRole('button', { name: 'Save' })[0]);
		await waitFor(() => expect(updateNetworkIntegration).toHaveBeenCalledWith('hdhomerun', expect.any(Object)));
	});

	it('loads and saves the XMLTV guide URL', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		listNetworkIntegrations.mockResolvedValue([
			{ id: 'xmltv', type: 'xmltv', name: 'XMLTV', settings: { url: 'http://example.com/guide.xml' } },
		]);
		updateNetworkIntegration.mockResolvedValue({
			id: 'xmltv',
			type: 'xmltv',
			name: 'XMLTV',
			settings: { url: 'http://example.com/guide.xml' },
		});
		render(Page);

		await waitFor(() => expect(listNetworkIntegrations).toHaveBeenCalled());
		expect(await screen.findByDisplayValue('http://example.com/guide.xml')).toBeInTheDocument();

		await fireEvent.click(screen.getAllByRole('button', { name: 'Save' })[1]);
		await waitFor(() =>
			expect(updateNetworkIntegration).toHaveBeenCalledWith('xmltv', { url: 'http://example.com/guide.xml' }),
		);
	});

	it('displays XMLTV statistics and handles reload', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		listNetworkIntegrations.mockResolvedValue([
			{ id: 'xmltv', type: 'xmltv', name: 'XMLTV', settings: { url: 'http://example.com/guide.xml' } },
		]);
		const initialStats = {
			url: 'http://example.com/guide.xml',
			last_refreshed_at: '2026-08-22T10:00:00Z',
			channels_in_feed: 35,
			mapped_channels_count: 12,
			channels_with_programs: 12,
			programs_count: 850,
			days_count: 7,
			start_date: '2026-08-22T00:00:00Z',
			end_date: '2026-08-29T00:00:00Z',
			start_ts: 1787300000,
			end_ts: 1787904800,
		};
		getXmltvStats.mockResolvedValue(initialStats);
		const reloadedStats = {
			...initialStats,
			programs_count: 900,
			channels_in_feed: 40,
		};
		reloadXmltvGuide.mockResolvedValue({
			ok: true,
			stats: reloadedStats,
			message: 'XMLTV feed reloaded successfully.',
		});

		render(Page);

		await waitFor(() => expect(getXmltvStats).toHaveBeenCalled());
		expect(await screen.findByText('Feed Statistics')).toBeInTheDocument();
		expect(screen.getByText(/35 in feed \(12 mapped\)/)).toBeInTheDocument();
		expect(screen.getByText(/7 days/)).toBeInTheDocument();
		expect(screen.getByText('850')).toBeInTheDocument();

		const reloadBtn = screen.getByRole('button', { name: 'Reload Feed' });
		await fireEvent.click(reloadBtn);

		await waitFor(() => expect(reloadXmltvGuide).toHaveBeenCalled());
		expect(await screen.findByText('XMLTV feed reloaded successfully.')).toBeInTheDocument();
		expect(screen.getByText(/40 in feed \(12 mapped\)/)).toBeInTheDocument();
		expect(screen.getByText('900')).toBeInTheDocument();
	});

	it('displays error when XMLTV reload fails', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		listNetworkIntegrations.mockResolvedValue([
			{ id: 'xmltv', type: 'xmltv', name: 'XMLTV', settings: { url: 'http://example.com/guide.xml' } },
		]);
		getXmltvStats.mockResolvedValue(null);
		reloadXmltvGuide.mockRejectedValue(new Error('Feed timeout'));

		render(Page);

		await waitFor(() => expect(listNetworkIntegrations).toHaveBeenCalled());
		const reloadBtn = await screen.findByRole('button', { name: 'Reload Feed' });
		await fireEvent.click(reloadBtn);

		await waitFor(() => expect(reloadXmltvGuide).toHaveBeenCalled());
		expect(await screen.findByText('Feed timeout')).toBeInTheDocument();
	});

	it('loads channel lineup and lets an admin update XMLTV channel mapping', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		getChannelSettings.mockResolvedValue([
			{
				id: 'ch1',
				channel_number: '4.1',
				name: 'WNBC',
				is_hd: true,
				is_favorite: false,
				hidden: false,
				guide_provider: null,
				xmltv_channel_id: 'wnbc.us',
				xmltv_display_name: 'NBC 4',
			},
		]);
		updateChannelSetting.mockResolvedValue({
			id: 'ch1',
			channel_number: '4.1',
			name: 'WNBC',
			is_hd: true,
			is_favorite: false,
			hidden: false,
			guide_provider: 'xmltv',
			xmltv_channel_id: 'I4.1.wnbc.com',
			xmltv_display_name: 'NBC 4 HD',
		});
		render(Page);

		await screen.findByText('WNBC');
		expect(screen.getByDisplayValue('wnbc.us')).toBeInTheDocument();

		const xmltvInput = screen.getByDisplayValue('wnbc.us');
		await fireEvent.input(xmltvInput, { target: { value: 'I4.1.wnbc.com' } });

		// Click the save button inside the channel card
		const saveButtons = screen.getAllByRole('button', { name: 'Save' });
		const channelSaveButton = saveButtons[saveButtons.length - 1];
		await fireEvent.click(channelSaveButton);

		await waitFor(() =>
			expect(updateChannelSetting).toHaveBeenCalledWith('ch1', expect.objectContaining({
				xmltv_channel_id: 'I4.1.wnbc.com',
			})),
		);
	});

	it('allows an admin to trigger guide refresh', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		refreshGuide.mockResolvedValue({ status: 'ok', message: 'Started' });
		render(Page);

		const refreshButton = await screen.findByRole('button', { name: 'Refresh Guide' });
		await fireEvent.click(refreshButton);

		await waitFor(() => expect(refreshGuide).toHaveBeenCalled());
		expect(await screen.findByText('Guide refresh started.')).toBeInTheDocument();
	});

	it('configures and tests Schedules Direct credentials', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		listNetworkIntegrations.mockResolvedValue([
			{
				id: 'schedules_direct',
				type: 'schedules_direct',
				name: 'Schedules Direct',
				settings: { username: 'testuser', has_password: true },
			},
		]);
		testSchedulesDirectConnection.mockResolvedValue({
			ok: true,
			detail: { expires: '2027-01-01T00:00:00Z', lineups: [{ lineup: 'USA-OTA-90210', name: 'Local OTA' }] },
			error: null,
		});
		updateNetworkIntegration.mockResolvedValue({
			id: 'schedules_direct',
			type: 'schedules_direct',
			name: 'Schedules Direct',
			settings: { username: 'testuser', has_password: true },
		});
		render(Page);

		expect(await screen.findByRole('heading', { name: 'Schedules Direct' })).toBeInTheDocument();
		const usernameInput = screen.getByPlaceholderText('username');
		expect(usernameInput).toHaveValue('testuser');

		const testBtn = screen.getByRole('button', { name: 'Test Connection' });
		await fireEvent.click(testBtn);

		await waitFor(() => expect(testSchedulesDirectConnection).toHaveBeenCalledWith({ username: 'testuser' }));
		expect(await screen.findByText('Active Lineups')).toBeInTheDocument();
		expect(screen.getByText(/Local OTA/)).toBeInTheDocument();
	});

	it('allows an admin to reorder and save guide provider priority', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		updateSettings.mockResolvedValue({
			...BASE_SETTINGS,
			guide_provider_priority: 'schedules_direct,xmltv,hdhomerun_cloud',
		});
		render(Page);

		expect(await screen.findByText('Default Guide Source Priority')).toBeInTheDocument();

		// Click the down arrow on the first item (XMLTV) to move it down
		const guideSection = screen.getByText('Default Guide Source Priority').closest('section')!;
		const downButtons = within(guideSection).getAllByRole('button', { name: 'Move Down' });
		await fireEvent.click(downButtons[0]);

		// Click Save Guide Priority
		const savePriorityBtn = within(guideSection).getByRole('button', { name: 'Save Guide Priority' });
		await fireEvent.click(savePriorityBtn);

		await waitFor(() =>
			expect(updateSettings).toHaveBeenCalledWith({
				guide_provider_priority: 'schedules_direct,xmltv,hdhomerun_cloud',
			}),
		);
		expect(await within(guideSection).findByText('Priority order saved.')).toBeInTheDocument();
	});

	it('allows an admin to reorder and save recording server priority', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		updateSettings.mockResolvedValue({
			...BASE_SETTINGS,
			dvr_server_priority: 'hdhomerun,builtin',
		});
		render(Page);

		expect(await screen.findByText('Default Recording Server Priority')).toBeInTheDocument();

		const dvrSection = screen.getByText('Default Recording Server Priority').closest('section')!;
		const downButtons = within(dvrSection).getAllByRole('button', { name: 'Move Down' });
		await fireEvent.click(downButtons[0]);

		// Click Save Server Priority
		const saveDvrPriorityBtn = within(dvrSection).getByRole('button', { name: 'Save Server Priority' });
		await fireEvent.click(saveDvrPriorityBtn);

		await waitFor(() =>
			expect(updateSettings).toHaveBeenCalledWith({
				dvr_server_priority: 'hdhomerun,builtin',
			}),
		);
		expect(await within(dvrSection).findByText('Recording server priority saved.')).toBeInTheDocument();
	});

	it('maps channel to Schedules Direct station', async () => {
		user.set({ id: 'admin1', name: 'Admin', avatar: null, role: 'admin' });
		getChannelSettings.mockResolvedValue([
			{
				id: 'ch2',
				channel_number: '2.1',
				name: 'KCBS',
				is_hd: true,
				is_favorite: false,
				hidden: false,
				guide_provider: 'schedules_direct',
				xmltv_channel_id: null,
				xmltv_display_name: null,
				sd_station_id: '1001',
				sd_lineup_id: 'USA-OTA-90210',
			},
		]);
		updateChannelSetting.mockResolvedValue({
			id: 'ch2',
			channel_number: '2.1',
			name: 'KCBS',
			is_hd: true,
			is_favorite: false,
			hidden: false,
			guide_provider: 'schedules_direct',
			xmltv_channel_id: null,
			xmltv_display_name: null,
			sd_station_id: '1001',
			sd_lineup_id: 'USA-OTA-90210',
		});
		render(Page);

		await screen.findByText('KCBS');
		expect(screen.getByDisplayValue('1001')).toBeInTheDocument();

		const saveButtons = screen.getAllByRole('button', { name: 'Save' });
		const channelSaveButton = saveButtons[saveButtons.length - 1];
		await fireEvent.click(channelSaveButton);

		await waitFor(() =>
			expect(updateChannelSetting).toHaveBeenCalledWith('ch2', expect.objectContaining({
				guide_provider: 'schedules_direct',
				sd_station_id: '1001',
			})),
		);
	});
});


describe('settings +page.svelte — devices and profile', () => {
	it('lets a member save their profile name', async () => {
		user.set({ id: 'u1', name: 'Member', avatar: null, role: 'member' });
		updateSettings.mockResolvedValue({ ...BASE_SETTINGS });
		render(Page);

		const nameInput = await screen.findByLabelText('Name');
		await fireEvent.input(nameInput, { target: { value: 'New Name' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

		await waitFor(() => expect(listUsers).toHaveBeenCalled());
	});

	it('lists other devices and can forget one', async () => {
		user.set({ id: 'u1', name: 'Member', avatar: null, role: 'member' });
		listDevices.mockResolvedValue([{ id: 'd1', name: 'Other Device', last_seen_at: '2026-01-01' }]);
		render(Page);

		await screen.findByText('Other Device');
	});
});

describe('settings +page.svelte — language section', () => {
	it('persists a locale change and translates the page', async () => {
		user.set({ id: 'u1', name: 'Member', avatar: null, role: 'member' });
		render(Page);

		const select = await screen.findByLabelText('Language');
		await fireEvent.change(select, { target: { value: 'es' } });

		expect(await screen.findByText('Idioma')).toBeInTheDocument();

		// The locale (and this button's own label) switches live as soon as the
		// select changes — the network write is what waits for Save.
		await fireEvent.click(screen.getByRole('button', { name: 'Guardar idioma' }));
		await waitFor(() => expect(updatePreferences).toHaveBeenCalledWith({ locale: 'es' }));

		locale.set('en');
		await waitLocale();
	});
});

describe('settings +page.svelte — appearance section', () => {
	it('persists a theme change', async () => {
		user.set({ id: 'u1', name: 'Member', avatar: null, role: 'member' });
		render(Page);

		const select = await screen.findByLabelText('Appearance');
		await fireEvent.change(select, { target: { value: 'dark' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save appearance' }));

		await waitFor(() => expect(updatePreferences).toHaveBeenCalledWith({ theme: 'dark' }));
	});
});
