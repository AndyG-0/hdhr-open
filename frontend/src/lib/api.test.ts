import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE_URL: 'http://api.test' } }));

const { api, DEFAULT_FETCH_TIMEOUT_MS } = await import('./api');
const defaultSignal = expect.any(AbortSignal);

describe('api', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	it('themes fetches the theme endpoint', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({ ok: true, json: async () => ({ themes: [], default: 'dark' }) }),
		);

		const result = await api.themes();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/theme', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual({ themes: [], default: 'dark' });
	});

	it('settings fetches the settings endpoint', async () => {
		const settings = { timezone: 'UTC' };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => settings }));

		const result = await api.settings();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/settings', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(settings);
	});

	it('updateSettings PATCHes the settings endpoint with a JSON body', async () => {
		const partial = { timezone: 'America/Chicago' };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => partial }));

		await api.updateSettings(partial);

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/settings', {
			method: 'PATCH',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(partial),
			credentials: 'include',
			signal: defaultSignal,
		});
	});

	it('throws a descriptive error when the response is not ok', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));

		await expect(api.settings()).rejects.toThrow('Request to /api/settings failed: 500');
	});

	it('getHDHomeRunGuide fetches the guide endpoint', async () => {
		const channels = [{ channel_number: '5.1', channel_name: 'KXAS', airings: [] }];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => channels }));

		const result = await api.getHDHomeRunGuide();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(channels);
	});

	it('getHDHomeRunGuide appends start/end as query params when provided', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }));

		await api.getHDHomeRunGuide(1000, 2000);

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide?start=1000&end=2000', {
			credentials: 'include',
			signal: defaultSignal,
		});
	});

	it('getHDHomeRunChannels fetches the guide/channels endpoint', async () => {
		const body = { channels: [], guide_available: true };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => body }));

		const result = await api.getHDHomeRunChannels();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide/channels', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(body);
	});

	it('hdhomerunPlaybackUrl resolves a relative proxy path against the API base', () => {
		expect(api.hdhomerunPlaybackUrl('/api/hdhomerun/tuner1/stream')).toBe(
			'http://api.test/api/hdhomerun/tuner1/stream',
		);
	});

	it('hdhomerunPlaybackUrl leaves an absolute URL untouched', () => {
		expect(api.hdhomerunPlaybackUrl('http://tuner.local/stream')).toBe('http://tuner.local/stream');
	});

	it('addHDHomeRunRecordingRule POSTs the rule and returns the updated rule list', async () => {
		const rules = [{ RecordingRuleID: 'r1', SeriesID: 's1', Title: 'Show' }];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => rules }));

		const result = await api.addHDHomeRunRecordingRule({ series_id: 's1' });

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/dvr/recording-rules', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ series_id: 's1' }),
		});
		expect(result).toEqual(rules);
	});

	it('addHDHomeRunRecordingRule POSTs a keyword rule with no series_id', async () => {
		const rules = [{ RecordingRuleID: 'r2', SeriesID: 'college football', Title: 'College Football' }];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => rules }));

		const result = await api.addHDHomeRunRecordingRule({
			title: 'College Football',
			title_match_mode: 'exact',
			keyword_query: 'Ohio State',
		});

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/dvr/recording-rules', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ title: 'College Football', title_match_mode: 'exact', keyword_query: 'Ohio State' }),
		});
		expect(result).toEqual(rules);
	});

	it('deleteHDHomeRunRecordingRule DELETEs the given rule endpoint', async () => {
		const rules: unknown[] = [];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => rules }));

		await api.deleteHDHomeRunRecordingRule('r1');

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/dvr/recording-rules/r1', {
			method: 'DELETE',
			credentials: 'include',
			signal: defaultSignal,
		});
	});

	it('listNetworkIntegrations fetches the network-settings endpoint', async () => {
		const rows = [{ id: 'hdhomerun', type: 'hdhomerun', name: 'HDHomeRun', settings: {} }];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => rows }));

		const result = await api.listNetworkIntegrations();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/network-settings', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(rows);
	});

	it('updateNetworkIntegration PATCHes the given integration type', async () => {
		const updated = { id: 'hdhomerun', type: 'hdhomerun', name: 'HDHomeRun', settings: { tuner_host: 'hdhr.local' } };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => updated }));

		const result = await api.updateNetworkIntegration('hdhomerun', { tuner_host: 'hdhr.local' });

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/network-settings/hdhomerun', {
			method: 'PATCH',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ tuner_host: 'hdhr.local' }),
		});
		expect(result).toEqual(updated);
	});

	it('testHDHomeRunTunerConnection POSTs to the tuner test-connection endpoint', async () => {
		const result = { ok: true, detail: 'Connected', error: null };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => result }));

		const response = await api.testHDHomeRunTunerConnection({ tuner_host: 'hdhr.local' });

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/network-settings/hdhomerun/test-tuner-connection', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ tuner_host: 'hdhr.local' }),
		});
		expect(response).toEqual(result);
	});

	it('testHDHomeRunDvrConnection POSTs to the DVR test-connection endpoint', async () => {
		const result = { ok: true, detail: 'Connected', error: null };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => result }));

		const response = await api.testHDHomeRunDvrConnection({ dvr_host: 'dvr.local' });

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/network-settings/hdhomerun/test-dvr-connection', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ dvr_host: 'dvr.local' }),
		});
		expect(response).toEqual(result);
	});

	it('listUsers fetches the users endpoint', async () => {
		const profiles = [{ id: 'default', name: 'Default', avatar: null, has_pin: false }];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => profiles }));

		const result = await api.listUsers();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(profiles);
	});

	it('createUser POSTs the name, and omits avatar/pin when not provided', async () => {
		const me = { id: 'u1', name: 'Alice', avatar: null };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => me }));

		const result = await api.createUser('Alice');

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: 'Alice' }),
		});
		expect(result).toEqual(me);
	});

	it('createUser includes avatar and pin when provided', async () => {
		const me = { id: 'u1', name: 'Alice', avatar: '🐱' };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => me }));

		await api.createUser('Alice', '🐱', '1234');

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: 'Alice', avatar: '🐱', pin: '1234' }),
		});
	});

	it('loginUser POSTs a JSON body even when no PIN is given, since the backend requires one', async () => {
		const me = { id: 'u1', name: 'Alice', avatar: null };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => me }));

		const result = await api.loginUser('u1');

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users/u1/login', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({}),
		});
		expect(result).toEqual(me);
	});

	it('loginUser sends the PIN when provided', async () => {
		const me = { id: 'u1', name: 'Alice', avatar: null };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => me }));

		await api.loginUser('u1', '1234');

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users/u1/login', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ pin: '1234' }),
		});
	});

	it('logoutUser POSTs to the logout endpoint', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }));

		await api.logoutUser();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users/logout', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
		});
	});

	it('currentUser fetches the current user endpoint', async () => {
		const me = { id: 'u1', name: 'Alice', avatar: null };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => me }));

		const result = await api.currentUser();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users/me', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(me);
	});

	it('updateUser PATCHes the current user endpoint', async () => {
		const me = { id: 'u1', name: 'Alicia', avatar: null };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => me }));

		const result = await api.updateUser({ name: 'Alicia' });

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users/me', {
			method: 'PATCH',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: 'Alicia' }),
		});
		expect(result).toEqual(me);
	});

	it('deleteUser DELETEs the current user endpoint', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }));

		await api.deleteUser();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users/me', {
			method: 'DELETE',
			credentials: 'include',
			signal: defaultSignal,
		});
	});

	it('getPreferences fetches the current user preferences endpoint', async () => {
		const prefs = { theme: 'sepia' };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => prefs }));

		const result = await api.getPreferences();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users/me/preferences', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(prefs);
	});

	it('updatePreferences PATCHes the current user preferences endpoint', async () => {
		const prefs = { theme: 'sepia' };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => prefs }));

		const result = await api.updatePreferences({ theme: 'sepia' });

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/users/me/preferences', {
			method: 'PATCH',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ theme: 'sepia' }),
		});
		expect(result).toEqual(prefs);
	});

	it('setupStatus fetches the setup status endpoint', async () => {
		const status = { needs_setup: false };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => status }));

		const result = await api.setupStatus();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/setup/status', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(status);
	});

	it('listHouseholdUsers fetches the admin users endpoint', async () => {
		const members = [
			{ id: 'u1', name: 'Alice', avatar: null, has_pin: false, role: 'admin', created_at: '2026-01-01' },
		];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => members }));

		const result = await api.listHouseholdUsers();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/admin/users', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(members);
	});

	it('updateUserRole PATCHes the given member endpoint with the new role', async () => {
		const member = { id: 'u1', name: 'Alice', avatar: null, has_pin: false, role: 'admin', created_at: '2026-01-01' };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => member }));

		const result = await api.updateUserRole('u1', 'admin');

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/admin/users/u1/role', {
			method: 'PATCH',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ role: 'admin' }),
		});
		expect(result).toEqual(member);
	});

	it('createHouseholdUser POSTs payload to admin users endpoint', async () => {
		const created = { id: 'u2', name: 'Bob', avatar: '🦊', has_pin: true, role: 'member', created_at: '2026-01-02' };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => created }));

		const result = await api.createHouseholdUser({ name: 'Bob', avatar: '🦊', pin: '1234', role: 'member' });

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/admin/users', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: 'Bob', avatar: '🦊', pin: '1234', role: 'member' }),
		});
		expect(result).toEqual(created);
	});

	it('updateHouseholdUser PATCHes the given user endpoint with payload', async () => {
		const updated = { id: 'u2', name: 'Bobby', avatar: '🦊', has_pin: false, role: 'admin', created_at: '2026-01-02' };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => updated }));

		const result = await api.updateHouseholdUser('u2', { name: 'Bobby', pin: '', role: 'admin' });

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/admin/users/u2', {
			method: 'PATCH',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: 'Bobby', pin: '', role: 'admin' }),
		});
		expect(result).toEqual(updated);
	});

	it('removeHouseholdUser DELETEs the given member endpoint', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) }));

		await api.removeHouseholdUser('u1');

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/admin/users/u1', {
			method: 'DELETE',
			credentials: 'include',
			signal: defaultSignal,
		});
	});

	it('getChannelSettings fetches the guide channels settings endpoint', async () => {
		const channels = [
			{
				id: 'ch1',
				channel_number: '4.1',
				name: 'WNBC',
				is_hd: true,
				is_favorite: false,
				hidden: false,
				guide_provider: null,
				xmltv_channel_id: 'wnbc.us',
				xmltv_display_name: 'NBC',
			},
		];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => channels }));

		const result = await api.getChannelSettings();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide/channels/settings', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(channels);
	});

	it('updateChannelSetting PATCHes the specific channel settings', async () => {
		const payload = { guide_provider: 'xmltv' as const, xmltv_channel_id: 'wnbc.us' };
		const updated = { id: 'ch1', channel_number: '4.1', name: 'WNBC', ...payload };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => updated }));

		const result = await api.updateChannelSetting('ch1', payload);

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide/channels/ch1', {
			method: 'PATCH',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(payload),
		});
		expect(result).toEqual(updated);
	});

	it('getXmltvFeedChannels fetches available feed channels', async () => {
		const feedChannels = [{ xmltv_channel_id: 'wnbc.us', display_names: ['WNBC', 'NBC 4'] }];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => feedChannels }));

		const result = await api.getXmltvFeedChannels();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide/xmltv-feed-channels', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(feedChannels);
	});

	it('testSchedulesDirectConnection POSTs to the Schedules Direct test endpoint', async () => {
		const payload = { username: 'u1', password: 'p1' };
		const response = { ok: true, detail: { expires: '2027-01-01T00:00:00Z', lineups: [] }, error: null };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => response }));

		const result = await api.testSchedulesDirectConnection(payload);

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/network-settings/schedules-direct/test-connection', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(payload),
		});
		expect(result).toEqual(response);
	});

	it('getSchedulesDirectLineups fetches user active lineups', async () => {
		const lineups = [{ lineup: 'USA-OTA-90210', name: 'Local OTA' }];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => lineups }));

		const result = await api.getSchedulesDirectLineups();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/network-settings/schedules-direct/lineups', {
			credentials: 'include',
			signal: defaultSignal,
		});
		expect(result).toEqual(lineups);
	});

	it('getSchedulesDirectHeadends fetches available headends for a postal code', async () => {
		const headends = [{ headend: '90210', lineups: [] }];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => headends }));

		const result = await api.getSchedulesDirectHeadends('90210');

		expect(fetch).toHaveBeenCalledWith(
			'http://api.test/api/network-settings/schedules-direct/headends?postal_code=90210&country=USA',
			{ credentials: 'include', signal: defaultSignal }
		);
		expect(result).toEqual(headends);
	});

	it('addSchedulesDirectLineup POSTs to the lineup endpoint', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ code: 0 }) }));

		const result = await api.addSchedulesDirectLineup('USA-OTA-90210');

		expect(fetch).toHaveBeenCalledWith(
			'http://api.test/api/network-settings/schedules-direct/lineups/USA-OTA-90210',
			{ method: 'POST', credentials: 'include', signal: defaultSignal }
		);
		expect(result).toEqual({ code: 0 });
	});

	it('deleteSchedulesDirectLineup DELETEs the lineup endpoint', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ code: 0 }) }));

		const result = await api.deleteSchedulesDirectLineup('USA-OTA-90210');

		expect(fetch).toHaveBeenCalledWith(
			'http://api.test/api/network-settings/schedules-direct/lineups/USA-OTA-90210',
			{ method: 'DELETE', credentials: 'include', signal: defaultSignal }
		);
		expect(result).toEqual({ code: 0 });
	});

	it('getSchedulesDirectStations fetches available SD stations', async () => {
		const stations = [{ station_id: '1001', lineup_id: 'USA-OTA-90210', name: 'KCBS-DT' }];
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => stations }));

		const result = await api.getSchedulesDirectStations();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide/schedules-direct-stations', {
			credentials: 'include',
			signal: defaultSignal,
		});
		expect(result).toEqual(stations);
	});

	it('getXmltvStats fetches the XMLTV statistics endpoint', async () => {
		const stats = {
			url: 'http://example.com/guide.xml',
			last_refreshed_at: '2026-08-22T10:00:00Z',
			channels_in_feed: 42,
			mapped_channels_count: 10,
			channels_with_programs: 10,
			programs_count: 500,
			days_count: 7,
			start_date: '2026-08-22T00:00:00Z',
			end_date: '2026-08-29T00:00:00Z',
			start_ts: 1787300000,
			end_ts: 1787904800,
		};
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => stats }));

		const result = await api.getXmltvStats();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide/xmltv/stats', { credentials: 'include',
			signal: defaultSignal });
		expect(result).toEqual(stats);
	});

	it('reloadXmltvGuide POSTs to the XMLTV reload endpoint', async () => {
		const response = {
			ok: true,
			stats: {
				url: 'http://example.com/guide.xml',
				last_refreshed_at: '2026-08-22T10:00:00Z',
				channels_in_feed: 42,
				mapped_channels_count: 10,
				channels_with_programs: 10,
				programs_count: 500,
				days_count: 7,
				start_date: '2026-08-22T00:00:00Z',
				end_date: '2026-08-29T00:00:00Z',
				start_ts: 1787300000,
				end_ts: 1787904800,
			},
			message: 'XMLTV guide reloaded successfully',
		};
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => response }));

		const result = await api.reloadXmltvGuide();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide/xmltv/reload', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
		});
		expect(result).toEqual(response);
	});

	it('refreshGuide POSTs to the guide refresh endpoint', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'ok', message: 'Started' }) }));

		const result = await api.refreshGuide();

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/guide/refresh', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
		});
		expect(result).toEqual({ status: 'ok', message: 'Started' });
	});

	it('terminateTuner POSTs to the tuner termination endpoint', async () => {
		const response = { ok: true, message: 'Tuner 0 released', tuners: [] };
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => response }));

		const result = await api.terminateTuner(0);

		expect(fetch).toHaveBeenCalledWith('http://api.test/api/tuner/0/terminate', {
			method: 'POST',
			credentials: 'include',
			signal: defaultSignal,
		});
		expect(result).toEqual(response);
	});

	it('exports DEFAULT_FETCH_TIMEOUT_MS configured to 30000ms', () => {
		expect(DEFAULT_FETCH_TIMEOUT_MS).toBe(30_000);
	});

	it('rejects when request signal aborts due to timeout', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockImplementation((_url, init?: RequestInit) => {
				if (init?.signal) {
					return Promise.reject(new DOMException('The operation was aborted due to timeout', 'TimeoutError'));
				}
				return Promise.resolve({ ok: true, json: async () => ({}) });
			}),
		);

		await expect(api.settings()).rejects.toThrow('The operation was aborted due to timeout');
	});
});

