<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import {
		api,
		type AppSettings,
		type DeviceListEntry,
		type HouseholdUser,
		type NetworkTestConnectionResult,
		type HDHomeRunTranscodePreset,
		type HWAccelDiagnostics,
		type HDHomeRunChannelSetting,
		type XMLTVFeedChannel,
		type XMLTVStats,
		type SchedulesDirectTestResult,
		type SchedulesDirectHeadend,
		type SchedulesDirectStation,
	} from '$lib/api';

	import { user, logout } from '$lib/stores/user';
	import { device as currentDevice, renameDevice as renameCurrentDevice } from '$lib/stores/device';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { locale, persistLocale } from '$lib/i18n';
	import { theme, persistTheme } from '$lib/stores/theme';

	let settings = $state<AppSettings | null>(null);
	let timezoneInput = $state('UTC');
	let timezoneOptions = $state<string[]>(['UTC']);
	let error = $state<string | null>(null);

	let timezoneSaving = $state(false);
	let timezoneSaved = $state(false);
	let timezoneError = $state<string | null>(null);

	// Name/avatar/PIN for the logged-in profile — separate save flow from
	// the app-wide settings above since it hits /api/users/me, not
	// /api/settings.
	let profileNameInput = $state('');
	let profileAvatarInput = $state('');
	let profilePinInput = $state('');
	let profileHasPin = $state(false);
	let profileSaving = $state(false);
	let profileSaved = $state(false);
	let profileError = $state<string | null>(null);
	let confirmingDeleteProfile = $state(false);
	let deletingProfile = $state(false);
	let profileInitialized = false;

	// $user loads asynchronously (see +layout.svelte's gate), so seed these
	// inputs the first time it becomes available rather than in onMount.
	$effect(() => {
		if ($user && !profileInitialized) {
			profileInitialized = true;
			profileNameInput = $user.name;
			profileAvatarInput = $user.avatar ?? '';
			const currentUserId = $user.id;
			api
				.listUsers()
				.then((profiles) => {
					profileHasPin = profiles.find((p) => p.id === currentUserId)?.has_pin ?? false;
				})
				.catch(() => {
					// leave the PIN section assuming no PIN is set
				});
		}
	});

	// /api/settings is admin-only — load it lazily once $user is known to be
	// an admin, mirroring profileInitialized below, so a member never fires a
	// request that's guaranteed to 403.
	let settingsInitialized = false;

	$effect(() => {
		if ($user?.role === 'admin' && !settingsInitialized) {
			settingsInitialized = true;
			loadSettings();
		}
	});

	const VALID_GUIDE_PROVIDERS = ['xmltv', 'schedules_direct', 'hdhomerun_cloud'] as const;
	type GuideProviderId = (typeof VALID_GUIDE_PROVIDERS)[number];

	let guidePriorityList = $state<GuideProviderId[]>(['xmltv', 'schedules_direct', 'hdhomerun_cloud']);
	let guidePrioritySaving = $state(false);
	let guidePrioritySaved = $state(false);
	let guidePriorityError = $state<string | null>(null);

	const VALID_DVR_SERVERS = ['builtin', 'hdhomerun'] as const;
	type DvrServerId = (typeof VALID_DVR_SERVERS)[number];

	let dvrPriorityList = $state<DvrServerId[]>(['builtin', 'hdhomerun']);
	let dvrPrioritySaving = $state(false);
	let dvrPrioritySaved = $state(false);
	let dvrPriorityError = $state<string | null>(null);

	function parseGuidePriority(raw: string | undefined): GuideProviderId[] {
		const items = (raw ?? '')
			.split(',')
			.map((s) => s.trim())
			.filter((s): s is GuideProviderId => VALID_GUIDE_PROVIDERS.includes(s as GuideProviderId));
		for (const p of VALID_GUIDE_PROVIDERS) {
			if (!items.includes(p)) items.push(p);
		}
		return items;
	}

	function moveGuidePriorityUp(index: number) {
		if (index <= 0) return;
		const next = [...guidePriorityList];
		const temp = next[index - 1];
		next[index - 1] = next[index];
		next[index] = temp;
		guidePriorityList = next;
		guidePrioritySaved = false;
	}

	function moveGuidePriorityDown(index: number) {
		if (index >= guidePriorityList.length - 1) return;
		const next = [...guidePriorityList];
		const temp = next[index + 1];
		next[index + 1] = next[index];
		next[index] = temp;
		guidePriorityList = next;
		guidePrioritySaved = false;
	}

	function providerLabel(id: GuideProviderId): string {
		switch (id) {
			case 'xmltv':
				return get(_)('network_settings.guide_provider_xmltv');
			case 'schedules_direct':
				return get(_)('network_settings.guide_provider_schedules_direct');
			case 'hdhomerun_cloud':
				return get(_)('network_settings.guide_provider_hdhomerun');
		}
	}

	function parseDvrPriority(raw: string | undefined): DvrServerId[] {
		const items = (raw ?? '')
			.split(',')
			.map((s) => s.trim())
			.filter((s): s is DvrServerId => VALID_DVR_SERVERS.includes(s as DvrServerId));
		for (const s of VALID_DVR_SERVERS) {
			if (!items.includes(s)) items.push(s);
		}
		return items;
	}

	function moveDvrPriorityUp(index: number) {
		if (index <= 0) return;
		const next = [...dvrPriorityList];
		const temp = next[index - 1];
		next[index - 1] = next[index];
		next[index] = temp;
		dvrPriorityList = next;
		dvrPrioritySaved = false;
	}

	function moveDvrPriorityDown(index: number) {
		if (index >= dvrPriorityList.length - 1) return;
		const next = [...dvrPriorityList];
		const temp = next[index + 1];
		next[index + 1] = next[index];
		next[index] = temp;
		dvrPriorityList = next;
		dvrPrioritySaved = false;
	}

	function dvrServerLabel(id: DvrServerId): string {
		switch (id) {
			case 'builtin':
				return get(_)('network_settings.dvr_provider_builtin');
			case 'hdhomerun':
				return get(_)('network_settings.dvr_provider_hdhomerun');
		}
	}

	function dvrServerDesc(id: DvrServerId): string {
		switch (id) {
			case 'builtin':
				return get(_)('network_settings.dvr_provider_builtin_desc');
			case 'hdhomerun':
				return get(_)('network_settings.dvr_provider_hdhomerun_desc');
		}
	}

	async function loadSettings() {
		try {
			settings = await api.settings();
			timezoneInput = settings.timezone;
			if (!timezoneOptions.includes(timezoneInput)) timezoneOptions = [timezoneInput, ...timezoneOptions];
			guidePriorityList = parseGuidePriority(settings.guide_provider_priority);
			dvrPriorityList = parseDvrPriority(settings.dvr_server_priority);
		} catch {
			error = 'Could not load settings.';
		}
	}

	let householdUsers = $state<HouseholdUser[]>([]);
	let householdError = $state<string | null>(null);
	let householdLoading = $state(false);
	let updatingRoleId = $state<string | null>(null);
	let confirmingRemoveId = $state<string | null>(null);
	let removingId = $state<string | null>(null);
	let householdInitialized = false;

	$effect(() => {
		if ($user?.role === 'admin' && !householdInitialized) {
			householdInitialized = true;
			loadHouseholdUsers();
		}
	});

	async function loadHouseholdUsers() {
		householdLoading = true;
		householdError = null;
		try {
			householdUsers = await api.listHouseholdUsers();
		} catch {
			householdError = 'Could not load household members.';
		} finally {
			householdLoading = false;
		}
	}

	async function toggleRole(member: HouseholdUser) {
		const nextRole = member.role === 'admin' ? 'member' : 'admin';
		updatingRoleId = member.id;
		householdError = null;
		try {
			const updated = await api.updateUserRole(member.id, nextRole);
			householdUsers = householdUsers.map((existing) => (existing.id === member.id ? updated : existing));
		} catch {
			householdError = member.role === 'admin' ? "Can't demote the last remaining admin." : 'Could not update role.';
		} finally {
			updatingRoleId = null;
		}
	}

	async function removeMember(id: string) {
		removingId = id;
		householdError = null;
		try {
			await api.removeHouseholdUser(id);
			householdUsers = householdUsers.filter((u) => u.id !== id);
		} catch {
			householdError = 'Could not remove this member.';
		} finally {
			removingId = null;
			confirmingRemoveId = null;
		}
	}

	// HDHomeRun network settings (tuner/DVR connection + optional XMLTV guide
	// URL) — same admin-only load-gate pattern as loadSettings()/
	// loadHouseholdUsers() above, since /api/network-settings writes (and
	// this page's reads) are admin-only.
	let hdhomerunSettings = $state<Record<string, unknown>>({});
	let hdhomerunTunerHostInput = $state('');
	let hdhomerunTunerPortInput = $state(80);
	let hdhomerunDvrHostInput = $state('');
	let hdhomerunDvrPortInput = $state(59090);
	let hdhomerunSaving = $state(false);
	let hdhomerunError = $state<string | null>(null);
	let hdhomerunTestingTuner = $state(false);
	let hdhomerunTunerTestResult = $state<NetworkTestConnectionResult | null>(null);
	let hdhomerunTestingDvr = $state(false);
	let hdhomerunDvrTestResult = $state<NetworkTestConnectionResult | null>(null);

	// XMLTV guide feed — a separate network integration from the HDHomeRun
	// tuner/DVR connection above, so it has its own load/save flow against
	// the 'xmltv' network-integration type.
	let xmltvUrlInput = $state('');
	let xmltvSaving = $state(false);
	let xmltvError = $state<string | null>(null);
	let xmltvStats = $state<XMLTVStats | null>(null);
	let xmltvReloading = $state(false);
	let xmltvReloadMessage = $state<string | null>(null);
	let xmltvReloadError = $state<string | null>(null);

	// Schedules Direct settings
	let sdUsernameInput = $state('');
	let sdPasswordInput = $state('');
	let sdHasPassword = $state(false);
	let sdSaving = $state(false);
	let sdError = $state<string | null>(null);
	let sdTesting = $state(false);
	let sdTestResult = $state<SchedulesDirectTestResult | null>(null);
	let sdStations = $state<SchedulesDirectStation[]>([]);
	let sdPostalCodeInput = $state('');
	let sdHeadends = $state<SchedulesDirectHeadend[]>([]);
	let sdSearchingHeadends = $state(false);
	let sdHeadendsError = $state<string | null>(null);
	let sdAddingLineupId = $state<string | null>(null);
	let sdDeletingLineupId = $state<string | null>(null);

	// TMDB settings
	let tmdbApiKeyInput = $state('');
	let tmdbHasApiKey = $state(false);
	let tmdbSaving = $state(false);
	let tmdbError = $state<string | null>(null);

	let networkInitialized = false;

	$effect(() => {
		if ($user?.role === 'admin' && !networkInitialized) {
			networkInitialized = true;
			loadNetworkIntegrations();
		}
	});

	async function loadNetworkIntegrations() {
		try {
			const rows = await api.listNetworkIntegrations();

			const hdhomerun = rows.find((r) => r.type === 'hdhomerun');
			hdhomerunSettings = hdhomerun?.settings ?? {};
			hdhomerunTunerHostInput = (hdhomerunSettings.tuner_host as string) ?? '';
			hdhomerunTunerPortInput = (hdhomerunSettings.tuner_port as number) ?? 80;
			hdhomerunDvrHostInput = (hdhomerunSettings.dvr_host as string) ?? '';
			hdhomerunDvrPortInput = (hdhomerunSettings.dvr_port as number) ?? 59090;

			const xmltv = rows.find((r) => r.type === 'xmltv');
			xmltvUrlInput = (xmltv?.settings.url as string) ?? '';

			const sd = rows.find((r) => r.type === 'schedules_direct');
			sdUsernameInput = (sd?.settings.username as string) ?? '';
			sdHasPassword = Boolean(sd?.settings.has_password);

			const tmdb = rows.find((r) => r.type === 'tmdb');
			tmdbHasApiKey = Boolean(tmdb?.settings.has_api_key);

			playbackModeInput = (hdhomerunSettings.playback_mode as string) ?? 'server_transcode';
			hwaccelInput = (hdhomerunSettings.hwaccel as string) ?? 'software';
			customFfmpegArgsInput = (hdhomerunSettings.custom_ffmpeg_args as string) ?? '';
			hwaccelDeviceInput = (hdhomerunSettings.hwaccel_device as string) ?? '/dev/dri/renderD128';
			ffmpegDebugInput = (hdhomerunSettings.ffmpeg_debug as boolean) ?? false;
			thumbnailsEnabledInput = (hdhomerunSettings.thumbnails_enabled as boolean) ?? true;
			if (transcodePresets.length === 0) {
				try {
					transcodePresets = await api.hdhomerunTranscodePresets();
				} catch {
					transcodePresets = [];
				}
			}
			loadChannelSettings();
			loadXmltvStats();
		} catch {
			error = 'Could not load network settings.';
		}
	}


	function hdhomerunFormSettings(): Record<string, unknown> {
		return {
			tuner_host: hdhomerunTunerHostInput,
			tuner_port: hdhomerunTunerPortInput,
			dvr_host: hdhomerunDvrHostInput,
			dvr_port: hdhomerunDvrPortInput,
		};
	}

	async function testHdhomerunTuner() {
		hdhomerunTestingTuner = true;
		hdhomerunTunerTestResult = null;
		try {
			hdhomerunTunerTestResult = await api.testHDHomeRunTunerConnection(hdhomerunFormSettings());
		} catch {
			hdhomerunTunerTestResult = { ok: false, detail: null, error: get(_)('common.backend_unreachable') };
		} finally {
			hdhomerunTestingTuner = false;
		}
	}

	async function testHdhomerunDvr() {
		hdhomerunTestingDvr = true;
		hdhomerunDvrTestResult = null;
		try {
			hdhomerunDvrTestResult = await api.testHDHomeRunDvrConnection(hdhomerunFormSettings());
		} catch {
			hdhomerunDvrTestResult = { ok: false, detail: null, error: get(_)('common.backend_unreachable') };
		} finally {
			hdhomerunTestingDvr = false;
		}
	}

	async function saveHdhomerun() {
		hdhomerunSaving = true;
		hdhomerunError = null;
		try {
			const updated = await api.updateNetworkIntegration('hdhomerun', hdhomerunFormSettings());
			hdhomerunSettings = updated.settings;
		} catch {
			hdhomerunError = get(_)('network_settings.save_error');
		} finally {
			hdhomerunSaving = false;
		}
	}

	async function loadXmltvStats() {
		try {
			xmltvStats = await api.getXmltvStats();
		} catch {
			// keep stats as null
		}
	}

	async function saveXmltv() {
		xmltvSaving = true;
		xmltvError = null;
		xmltvReloadMessage = null;
		xmltvReloadError = null;
		try {
			await api.updateNetworkIntegration('xmltv', { url: xmltvUrlInput });
			api.getXmltvFeedChannels().then((fc) => (xmltvFeedChannels = fc)).catch(() => {});
			loadXmltvStats();
		} catch {
			xmltvError = get(_)('network_settings.save_error');
		} finally {
			xmltvSaving = false;
		}
	}

	async function reloadXmltv() {
		xmltvReloading = true;
		xmltvReloadMessage = null;
		xmltvReloadError = null;
		try {
			const res = await api.reloadXmltvGuide();
			xmltvStats = res.stats;
			xmltvReloadMessage = get(_)('network_settings.xmltv_reload_success');
			api.getXmltvFeedChannels().then((fc) => (xmltvFeedChannels = fc)).catch(() => {});
		} catch (err) {
			xmltvReloadError = err instanceof Error ? err.message : get(_)('network_settings.xmltv_reload_error');
		} finally {
			xmltvReloading = false;
		}
	}

	async function testSchedulesDirect() {
		sdTesting = true;
		sdTestResult = null;
		try {
			const payload: Record<string, unknown> = { username: sdUsernameInput };
			if (sdPasswordInput) payload.password = sdPasswordInput;
			sdTestResult = await api.testSchedulesDirectConnection(payload);
		} catch {
			sdTestResult = { ok: false, detail: null, error: get(_)('common.backend_unreachable') };
		} finally {
			sdTesting = false;
		}
	}

	async function saveSchedulesDirect() {
		sdSaving = true;
		sdError = null;
		try {
			const payload: Record<string, unknown> = { username: sdUsernameInput };
			if (sdPasswordInput) {
				payload.password = sdPasswordInput;
			}
			const res = await api.updateNetworkIntegration('schedules_direct', payload);
			sdHasPassword = Boolean(res.settings.has_password);
			sdPasswordInput = '';
			api.getSchedulesDirectStations().then((st) => (sdStations = st)).catch(() => {});
		} catch {
			sdError = get(_)('network_settings.save_error');
		} finally {
			sdSaving = false;
		}
	}

	async function saveTmdb() {
		tmdbSaving = true;
		tmdbError = null;
		try {
			const payload: Record<string, unknown> = {};
			if (tmdbApiKeyInput) {
				payload.api_key = tmdbApiKeyInput;
			}
			const res = await api.updateNetworkIntegration('tmdb', payload);
			tmdbHasApiKey = Boolean(res.settings.has_api_key);
			tmdbApiKeyInput = '';
		} catch {
			tmdbError = get(_)('network_settings.save_error');
		} finally {
			tmdbSaving = false;
		}
	}

	async function searchSdHeadends() {
		if (!sdPostalCodeInput.trim()) return;
		sdSearchingHeadends = true;
		sdHeadendsError = null;
		try {
			sdHeadends = await api.getSchedulesDirectHeadends(sdPostalCodeInput.trim());
		} catch {
			sdHeadendsError = get(_)('network_settings.save_error');
		} finally {
			sdSearchingHeadends = false;
		}
	}

	async function addSdLineup(lineupId: string) {
		sdAddingLineupId = lineupId;
		try {
			await api.addSchedulesDirectLineup(lineupId);
			if (sdTestResult?.detail) {
				const lineups = await api.getSchedulesDirectLineups();
				sdTestResult.detail.lineups = lineups;
			}
			api.getSchedulesDirectStations().then((st) => (sdStations = st)).catch(() => {});
		} catch {
			sdError = get(_)('network_settings.save_error');
		} finally {
			sdAddingLineupId = null;
		}
	}

	async function deleteSdLineup(lineupId: string) {
		sdDeletingLineupId = lineupId;
		try {
			await api.deleteSchedulesDirectLineup(lineupId);
			if (sdTestResult?.detail) {
				const lineups = await api.getSchedulesDirectLineups();
				sdTestResult.detail.lineups = lineups;
			}
			api.getSchedulesDirectStations().then((st) => (sdStations = st)).catch(() => {});
		} catch {
			sdError = get(_)('network_settings.save_error');
		} finally {
			sdDeletingLineupId = null;
		}
	}

	// Channel Lineup & XMLTV mapping state and methods
	let channelSettings = $state<HDHomeRunChannelSetting[]>([]);
	let channelSettingsLoading = $state(false);
	let channelSettingsError = $state<string | null>(null);
	let channelSavingId = $state<string | null>(null);
	let channelSavedId = $state<string | null>(null);
	let xmltvFeedChannels = $state<XMLTVFeedChannel[]>([]);
	let guideRefreshing = $state(false);
	let guideRefreshMessage = $state<string | null>(null);
	let guideRefreshError = $state<string | null>(null);

	async function loadChannelSettings() {
		channelSettingsLoading = true;
		channelSettingsError = null;
		try {
			const [channels, feedChannels, schedulesDirectStations] = await Promise.all([
				api.getChannelSettings().catch(() => []),
				api.getXmltvFeedChannels().catch(() => []),
				api.getSchedulesDirectStations().catch(() => []),
			]);
			channelSettings = channels;
			xmltvFeedChannels = feedChannels;
			sdStations = schedulesDirectStations;
		} catch {
			channelSettingsError = get(_)('network_settings.channel_save_error');
		} finally {
			channelSettingsLoading = false;
		}
	}

	async function saveChannelSetting(channel: HDHomeRunChannelSetting) {
		channelSavingId = channel.id;
		channelSavedId = null;
		channelSettingsError = null;
		try {
			const updated = await api.updateChannelSetting(channel.id, {
				guide_provider: channel.guide_provider,
				xmltv_channel_id: channel.xmltv_channel_id,
				xmltv_display_name: channel.xmltv_display_name,
				sd_station_id: channel.sd_station_id,
				sd_lineup_id: channel.sd_lineup_id,
				is_favorite: channel.is_favorite,
				hidden: channel.hidden,
			});
			channelSettings = channelSettings.map((c) => (c.id === channel.id ? updated : c));
			channelSavedId = channel.id;
			setTimeout(() => {
				if (channelSavedId === channel.id) channelSavedId = null;
			}, 2500);
		} catch {
			channelSettingsError = get(_)('network_settings.channel_save_error');
		} finally {
			channelSavingId = null;
		}
	}

	async function clearXmltvMapping(channel: HDHomeRunChannelSetting) {
		channel.xmltv_channel_id = '';
		channel.xmltv_display_name = '';
		await saveChannelSetting(channel);
	}

	async function clearSdMapping(channel: HDHomeRunChannelSetting) {
		channel.sd_station_id = '';
		channel.sd_lineup_id = '';
		await saveChannelSetting(channel);
	}

	async function handleRefreshGuide() {
		guideRefreshing = true;
		guideRefreshMessage = null;
		guideRefreshError = null;
		try {
			await api.refreshGuide();
			guideRefreshMessage = get(_)('network_settings.refresh_guide_success');
			await loadChannelSettings();
		} catch {
			guideRefreshError = get(_)('network_settings.refresh_guide_error');
		} finally {
			guideRefreshing = false;
		}
	}


	// Playback/transcode settings — a separate save flow (its own PATCH of
	// the same 'hdhomerun' network integration row) from the tuner/DVR
	// connection fields above, matching how the old widget-detail editor
	// kept them as distinct forms.
	let playbackModeInput = $state('server_transcode');
	let hwaccelInput = $state('software');
	let customFfmpegArgsInput = $state('');
	let hwaccelDeviceInput = $state('/dev/dri/renderD128');
	let ffmpegDebugInput = $state(false);
	let thumbnailsEnabledInput = $state(true);
	let playbackSaving = $state(false);
	let playbackError = $state<string | null>(null);
	let playbackSaved = $state(false);

	let transcodePresets = $state<HDHomeRunTranscodePreset[]>([]);
	const selectedPreset = $derived(transcodePresets.find((p) => p.id === hwaccelInput) ?? null);

	// Word-splits the way Python's shlex.split does — which is what the
	// backend uses on custom_ffmpeg_args (transcoding._output_args). A plain
	// split(/\s+/) disagrees with it on any quoted argument (a filter graph
	// with spaces, a path with a space), so the preview would show a command
	// the backend never runs.
	function shlexSplit(input: string): string[] {
		const tokens: string[] = [];
		// A quoted run, an escaped char, or a run of unquoted non-space.
		const pattern = /"((?:\\.|[^"\\])*)"|'([^']*)'|((?:\\.|[^\s'"\\])+)/g;
		let token = '';
		let end = 0;
		for (const match of input.matchAll(pattern)) {
			// A gap since the previous match means whitespace, i.e. a token
			// boundary; adjacent matches ("-vf"x'y') are one token.
			if (match.index > end && token) {
				tokens.push(token);
				token = '';
			}
			const [, doubleQuoted, singleQuoted, bare] = match;
			if (singleQuoted !== undefined) token += singleQuoted;
			else token += (doubleQuoted ?? bare).replace(/\\(.)/g, '$1');
			end = match.index + match[0].length;
		}
		if (token) tokens.push(token);
		return tokens;
	}

	// Mirrors transcoding.build_ffmpeg_args()'s argument order, so the
	// command shown while editing matches what saving would actually run.
	const livePreviewCommand = $derived.by(() => {
		if (!selectedPreset) return '';
		let outputArgs = selectedPreset.output_args;
		if (hwaccelInput === 'custom') {
			const trimmed = customFfmpegArgsInput.trim();
			outputArgs = trimmed
				? shlexSplit(trimmed)
				: (transcodePresets.find((p) => p.id === 'software')?.output_args ?? []);
		}
		const device = hwaccelDeviceInput.trim() || '/dev/dri/renderD128';
		const substitute = (args: string[]) => args.map((arg) => arg.replaceAll('{device}', device));
		return [
			'ffmpeg',
			'-hide_banner',
			'-loglevel',
			ffmpegDebugInput ? 'verbose' : 'warning',
			'-nostats',
			...substitute(selectedPreset.input_args),
			'-i',
			'<channel stream>',
			...substitute(outputArgs),
			'-f',
			'mpegts',
			'pipe:1',
		].join(' ');
	});

	let diagnostics = $state<HWAccelDiagnostics | null>(null);
	let diagnosticsRunning = $state(false);
	let diagnosticsError = $state<string | null>(null);

	async function runDiagnostics() {
		diagnosticsRunning = true;
		diagnosticsError = null;
		try {
			diagnostics = await api.hdhomerunHwaccelDiagnostics(hwaccelDeviceInput.trim() || undefined);
		} catch {
			diagnostics = null;
			diagnosticsError = get(_)('hdhomerun.detail.diagnostics_failed');
		} finally {
			diagnosticsRunning = false;
		}
	}

	function playbackFormSettings(): Record<string, unknown> {
		return {
			playback_mode: playbackModeInput,
			hwaccel: hwaccelInput,
			custom_ffmpeg_args: customFfmpegArgsInput,
			hwaccel_device: hwaccelDeviceInput.trim(),
			ffmpeg_debug: ffmpegDebugInput,
			thumbnails_enabled: thumbnailsEnabledInput,
		};
	}

	async function savePlayback() {
		playbackSaving = true;
		playbackError = null;
		playbackSaved = false;
		try {
			const updated = await api.updateNetworkIntegration('hdhomerun', playbackFormSettings());
			hdhomerunSettings = updated.settings;
			playbackSaved = true;
		} catch {
			playbackError = get(_)('common.connection_save_error');
		} finally {
			playbackSaving = false;
		}
	}

	let devices = $state<DeviceListEntry[]>([]);
	let devicesError = $state<string | null>(null);
	let deviceNameInput = $state('');
	let savingDeviceName = $state(false);
	let confirmingForgetDeviceId = $state<string | null>(null);
	let forgettingDeviceId = $state<string | null>(null);
	let deviceNameInitialized = false;
	let renamingDevice = $state(false);
	let renameDialogEl = $state<HTMLDivElement | null>(null);

	function cancelRenameDevice() {
		renamingDevice = false;
		deviceNameInput = $currentDevice?.name ?? '';
	}

	function handleRenameDialogPointerDown(e: PointerEvent) {
		if (renamingDevice && renameDialogEl && e.target instanceof Node && !renameDialogEl.contains(e.target)) {
			cancelRenameDevice();
		}
	}

	function handleRenameDialogKeydown(e: KeyboardEvent) {
		if (renamingDevice && e.key === 'Escape') cancelRenameDevice();
	}

	$effect(() => {
		if ($currentDevice && !deviceNameInitialized) {
			deviceNameInitialized = true;
			deviceNameInput = $currentDevice.name;
		}
	});

	async function loadDevices() {
		try {
			devices = await api.listDevices();
		} catch {
			devicesError = get(_)('settings.devices.load_error');
		}
	}

	// Fallback matches the backend's default set; refreshed from /api/theme
	// on mount so new themes show up without a frontend redeploy.
	let themeIds = $state(['light', 'dark', 'sepia', 'contrast', 'forest', 'ocean']);
	let themeNames = $state<Record<string, string>>({});

	// Language and theme both apply live to the DOM the instant the store is
	// set (see stores/theme.ts and $lib/i18n) — that live-preview stays, but
	// the server write (persistLocale/persistTheme) waits for Save like every
	// other section on this page, rather than firing on every selection.
	let localeSaving = $state(false);
	let localeSaved = $state(false);
	let localeError = $state<string | null>(null);

	let themeSaving = $state(false);
	let themeSaved = $state(false);
	let themeError = $state<string | null>(null);

	async function saveLocale() {
		localeSaving = true;
		localeError = null;
		try {
			await persistLocale($locale ?? 'en');
			localeSaved = true;
		} catch {
			localeError = get(_)('settings.language.save_error');
		} finally {
			localeSaving = false;
		}
	}

	async function saveTheme() {
		themeSaving = true;
		themeError = null;
		try {
			await persistTheme($theme);
			themeSaved = true;
		} catch {
			themeError = get(_)('settings.appearance.save_error');
		} finally {
			themeSaving = false;
		}
	}

	onMount(async () => {
		try {
			// Intl.supportedValuesOf isn't in every browser's types yet, but is
			// available in the Chromium the kiosk runs — avoids shipping a
			// hardcoded IANA timezone list.
			const supported = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.(
				'timeZone',
			);
			if (supported?.length) timezoneOptions = supported;
		} catch {
			// keep the UTC-only fallback
		}

		try {
			const { themes } = await api.themes();
			themeIds = themes.map((t) => t.id);
			themeNames = Object.fromEntries(themes.map((t) => [t.id, t.name]));
		} catch {
			// keep the fallback list
		}

		await loadDevices();
	});

	async function saveTimezone() {
		timezoneSaving = true;
		timezoneSaved = false;
		timezoneError = null;
		try {
			settings = await api.updateSettings({ timezone: timezoneInput });
			timezoneSaved = true;
		} catch {
			timezoneError = 'Could not save timezone.';
		} finally {
			timezoneSaving = false;
		}
	}

	async function saveGuidePriority() {
		guidePrioritySaving = true;
		guidePrioritySaved = false;
		guidePriorityError = null;
		try {
			const priorityStr = guidePriorityList.join(',');
			settings = await api.updateSettings({ guide_provider_priority: priorityStr });
			guidePrioritySaved = true;
		} catch {
			guidePriorityError = get(_)('network_settings.guide_priority_error');
		} finally {
			guidePrioritySaving = false;
		}
	}

	async function saveDvrPriority() {
		dvrPrioritySaving = true;
		dvrPrioritySaved = false;
		dvrPriorityError = null;
		try {
			const priorityStr = dvrPriorityList.join(',');
			settings = await api.updateSettings({ dvr_server_priority: priorityStr });
			dvrPrioritySaved = true;
		} catch {
			dvrPriorityError = get(_)('network_settings.dvr_priority_error');
		} finally {
			dvrPrioritySaving = false;
		}
	}

	async function saveProfile() {
		if (profilePinInput && !/^\d{4,8}$/.test(profilePinInput)) {
			profileError = get(_)('settings.profile.pin_invalid');
			return;
		}
		profileSaving = true;
		profileSaved = false;
		profileError = null;
		try {
			const partial: { name?: string; avatar?: string; pin?: string } = {
				name: profileNameInput.trim(),
				avatar: profileAvatarInput.trim(),
			};
			if (profilePinInput) partial.pin = profilePinInput;
			const updated = await api.updateUser(partial);
			user.set(updated);
			if (profilePinInput) profileHasPin = true;
			profilePinInput = '';
			profileSaved = true;
		} catch {
			profileError = get(_)('settings.profile.save_error');
		} finally {
			profileSaving = false;
		}
	}

	async function clearPin() {
		profileError = null;
		try {
			const updated = await api.updateUser({ pin: '' });
			user.set(updated);
			profileHasPin = false;
		} catch {
			profileError = get(_)('settings.profile.clear_pin_error');
		}
	}

	async function deleteProfile() {
		deletingProfile = true;
		profileError = null;
		try {
			await api.deleteUser();
			await logout().catch(() => {});
			goto('/login');
		} catch {
			profileError = get(_)('settings.profile.delete_error');
			deletingProfile = false;
			confirmingDeleteProfile = false;
		}
	}

	async function saveDeviceName() {
		savingDeviceName = true;
		devicesError = null;
		try {
			await renameCurrentDevice(deviceNameInput.trim());
			await loadDevices();
			renamingDevice = false;
		} catch {
			devicesError = get(_)('settings.devices.rename_error');
		} finally {
			savingDeviceName = false;
		}
	}

	async function forgetDevice(id: string) {
		forgettingDeviceId = id;
		devicesError = null;
		try {
			await api.deleteDevice(id);
			devices = devices.filter((d) => d.id !== id);
		} catch {
			devicesError = get(_)('settings.devices.forget_error');
		} finally {
			forgettingDeviceId = null;
			confirmingForgetDeviceId = null;
		}
	}
</script>

<svelte:window onpointerdown={handleRenameDialogPointerDown} onkeydown={handleRenameDialogKeydown} />

<div class="settings-page">
	<button class="back" onclick={() => goto('/')}>{$_('common.back')}</button>
	<h1>{$_('settings.page.title')}</h1>

	{#if $user?.role === 'admin'}
		<div class="settings-group">
			<h2 class="group-title">Admin settings</h2>
			<p class="group-subtitle">Shared across the whole household — visible only to admins.</p>

			<section>
				<h3>Household members</h3>
				{#if householdError}
					<p class="hint error">{householdError}</p>
				{/if}
				{#if householdLoading && householdUsers.length === 0}
					<p class="hint">Loading…</p>
				{:else}
					<ul class="member-list">
						{#each householdUsers as member (member.id)}
							<li>
								<span class="member-info">
									<span class="avatar-sm">{member.avatar || member.name.charAt(0).toUpperCase()}</span>
									<span class="member-name">{member.name}</span>
									<span class="role-badge" class:admin={member.role === 'admin'}>{member.role}</span>
								</span>
								{#if member.id === $user.id}
									<span class="hint">(you)</span>
								{:else}
									<span class="member-actions">
										<button class="clear" onclick={() => toggleRole(member)} disabled={updatingRoleId === member.id}>
											{member.role === 'admin' ? 'Demote to member' : 'Promote to admin'}
										</button>
										{#if confirmingRemoveId === member.id}
											<span class="confirm-actions">
												<button
													class="cancel"
													onclick={() => (confirmingRemoveId = null)}
													disabled={removingId === member.id}
												>
													Cancel
												</button>
												<button
													class="danger"
													onclick={() => removeMember(member.id)}
													disabled={removingId === member.id}
												>
													{removingId === member.id ? 'Removing…' : 'Remove'}
												</button>
											</span>
										{:else}
											<button class="danger-link" onclick={() => (confirmingRemoveId = member.id)}>Remove</button>
										{/if}
									</span>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			</section>

			{#if !settings}
				<p class="hint">{error ?? 'Loading…'}</p>
			{:else}
				<section>
					<h3>Timezone</h3>
					<label>
						Used to schedule recordings and display program times
						<select bind:value={timezoneInput}>
							{#each timezoneOptions as tz (tz)}
								<option value={tz}>{tz}</option>
							{/each}
						</select>
					</label>

					{#if timezoneError}
						<p class="hint error">{timezoneError}</p>
					{/if}
					{#if timezoneSaved}
						<p class="hint">Saved.</p>
					{/if}
					<button class="save" disabled={timezoneSaving} onclick={saveTimezone}>
						{timezoneSaving ? 'Saving…' : 'Save timezone'}
					</button>
				</section>
			{/if}

			<section>
				<h3>{$_('network_settings.section_hdhomerun')}</h3>
				<h4>{$_('hdhomerun.detail.tuner_heading')}</h4>
				<label>
					{$_('hdhomerun.detail.host_label')}
					<input type="text" bind:value={hdhomerunTunerHostInput} placeholder="hdhomerun.local" />
				</label>
				<label>
					{$_('hdhomerun.detail.port_label')}
					<input type="number" min="1" max="65535" bind:value={hdhomerunTunerPortInput} />
				</label>
				<div class="test-row">
					<button class="test" disabled={hdhomerunTestingTuner} onclick={testHdhomerunTuner}>
						{hdhomerunTestingTuner ? $_('common.testing') : $_('common.test_connection')}
					</button>
					{#if hdhomerunTunerTestResult}
						{#if hdhomerunTunerTestResult.ok}
							<span class="test-result ok"
								>{$_('network_settings.test_ok', { values: { detail: hdhomerunTunerTestResult.detail } })}</span
							>
						{:else}
							<span class="test-result fail"
								>{$_('network_settings.test_fail', { values: { error: hdhomerunTunerTestResult.error } })}</span
							>
						{/if}
					{/if}
				</div>

				<h4>
					{$_('hdhomerun.detail.dvr_settings_heading')} <span class="optional">{$_('hdhomerun.detail.optional')}</span>
				</h4>
				<label>
					{$_('hdhomerun.detail.host_label')}
					<input type="text" bind:value={hdhomerunDvrHostInput} placeholder="dvr.local" />
				</label>
				<label>
					{$_('hdhomerun.detail.port_label')}
					<input type="number" min="1" max="65535" bind:value={hdhomerunDvrPortInput} />
				</label>
				<div class="test-row">
					<button class="test" disabled={hdhomerunTestingDvr} onclick={testHdhomerunDvr}>
						{hdhomerunTestingDvr ? $_('common.testing') : $_('common.test_connection')}
					</button>
					{#if hdhomerunDvrTestResult}
						{#if hdhomerunDvrTestResult.ok}
							<span class="test-result ok"
								>{$_('network_settings.test_ok', { values: { detail: hdhomerunDvrTestResult.detail } })}</span
							>
						{:else}
							<span class="test-result fail"
								>{$_('network_settings.test_fail', { values: { error: hdhomerunDvrTestResult.error } })}</span
							>
						{/if}
					{/if}
				</div>

				{#if hdhomerunError}
					<p class="hint error">{hdhomerunError}</p>
				{/if}

				<button class="save" disabled={hdhomerunSaving} onclick={saveHdhomerun}>
					{hdhomerunSaving ? $_('common.saving') : $_('common.save')}
				</button>
			</section>

			<section>
				<h3>{$_('network_settings.section_xmltv')}</h3>
				<label>
					{$_('network_settings.xmltv_url_label')}
					<input type="text" bind:value={xmltvUrlInput} placeholder="http://example.com/guide.xml" />
				</label>
				<p class="hint">{$_('network_settings.xmltv_hint')}</p>

				{#if xmltvError}
					<p class="hint error">{xmltvError}</p>
				{/if}

				<div class="test-row">
					<button class="save" disabled={xmltvSaving} onclick={saveXmltv}>
						{xmltvSaving ? $_('common.saving') : $_('common.save')}
					</button>
					<button
						type="button"
						class="test"
						disabled={xmltvReloading || !xmltvUrlInput.trim()}
						onclick={reloadXmltv}
					>
						{xmltvReloading ? $_('network_settings.xmltv_reloading') : $_('network_settings.xmltv_reload_button')}
					</button>
				</div>

				{#if xmltvReloadMessage}
					<p class="hint ok">{xmltvReloadMessage}</p>
				{/if}
				{#if xmltvReloadError}
					<p class="hint error">{xmltvReloadError}</p>
				{/if}

				{#if xmltvStats}
					<div class="stats-panel">
						<h4>{$_('network_settings.xmltv_stats_heading')}</h4>
						<div class="stats-grid">
							<div class="stat-card">
								<span class="stat-label">{$_('network_settings.xmltv_stat_last_refreshed')}</span>
								<span class="stat-value">
									{xmltvStats.last_refreshed_at
										? new Date(xmltvStats.last_refreshed_at).toLocaleString()
										: $_('network_settings.xmltv_stat_never')}
								</span>
							</div>
							<div class="stat-card">
								<span class="stat-label">{$_('network_settings.xmltv_stat_channels')}</span>
								<span class="stat-value">
									{xmltvStats.channels_in_feed > 0 || xmltvStats.mapped_channels_count > 0
										? $_('network_settings.xmltv_stat_channels_detail', {
												values: {
													feed: xmltvStats.channels_in_feed,
													mapped: xmltvStats.mapped_channels_count
												}
											})
										: '0'}
								</span>
							</div>
							<div class="stat-card">
								<span class="stat-label">{$_('network_settings.xmltv_stat_days')}</span>
								<span class="stat-value">
									{xmltvStats.days_count > 0
										? $_('network_settings.xmltv_stat_days_value', {
												values: { count: xmltvStats.days_count }
											})
										: '0'}
								</span>
							</div>
							<div class="stat-card">
								<span class="stat-label">{$_('network_settings.xmltv_stat_dates')}</span>
								<span class="stat-value">
									{xmltvStats.start_date && xmltvStats.end_date
										? `${new Date(xmltvStats.start_date).toLocaleDateString()} – ${new Date(xmltvStats.end_date).toLocaleDateString()}`
										: $_('network_settings.xmltv_stat_no_data')}
								</span>
							</div>
							<div class="stat-card">
								<span class="stat-label">{$_('network_settings.xmltv_stat_programs')}</span>
								<span class="stat-value">
									{xmltvStats.programs_count > 0
										? xmltvStats.programs_count.toLocaleString()
										: '0'}
								</span>
							</div>
						</div>
					</div>
				{/if}
			</section>

			<section>
				<h3>{$_('network_settings.section_schedules_direct')}</h3>
				<p class="hint">{$_('network_settings.schedules_direct_hint')}</p>

				<label>
					{$_('network_settings.sd_username_label')}
					<input type="text" bind:value={sdUsernameInput} placeholder="username" />
				</label>
				<label>
					{$_('network_settings.sd_password_label')}
					<input
						type="password"
						bind:value={sdPasswordInput}
						placeholder={sdHasPassword ? '(unchanged)' : ''}
					/>
				</label>

				<div class="test-row">
					<button class="test" disabled={sdTesting} onclick={testSchedulesDirect}>
						{sdTesting ? $_('network_settings.sd_testing') : $_('network_settings.sd_test_connection')}
					</button>
					{#if sdTestResult}
						{#if sdTestResult.ok}
							<span class="test-result ok">
								{$_('network_settings.test_ok', { values: { detail: sdTestResult.detail?.expires ? $_('network_settings.sd_account_expires', { values: { expires: new Date(sdTestResult.detail.expires).toLocaleDateString() } }) : 'OK' } })}
							</span>
						{:else}
							<span class="test-result fail">
								{$_('network_settings.test_fail', { values: { error: sdTestResult.error } })}
							</span>
						{/if}
					{/if}
				</div>

				{#if sdTestResult?.detail?.lineups}
					<div class="sd-lineups-container">
						<h4>{$_('network_settings.sd_active_lineups')}</h4>
						{#if sdTestResult.detail.lineups.length === 0}
							<p class="hint">{$_('network_settings.sd_no_active_lineups')}</p>
						{:else}
							<ul class="sd-lineups-list">
								{#each sdTestResult.detail.lineups as lineup (lineup.lineup)}
									<li class="sd-lineup-item">
										<span>{lineup.name} ({lineup.lineup})</span>
										<button
											type="button"
											class="clear small"
											disabled={sdDeletingLineupId === lineup.lineup}
											onclick={() => deleteSdLineup(lineup.lineup)}
										>
											{$_('network_settings.sd_remove_lineup')}
										</button>
									</li>
								{/each}
							</ul>
						{/if}
					</div>
				{/if}

				<div class="sd-search-headends-container">
					<h4>{$_('network_settings.sd_search_headends_heading')}</h4>
					<div class="sd-search-row">
						<input
							type="text"
							bind:value={sdPostalCodeInput}
							placeholder={$_('network_settings.sd_postal_code_placeholder')}
						/>
						<button
							type="button"
							class="test"
							disabled={sdSearchingHeadends || !sdPostalCodeInput.trim()}
							onclick={searchSdHeadends}
						>
							{sdSearchingHeadends ? $_('network_settings.sd_searching') : $_('network_settings.sd_search_button')}
						</button>
					</div>

					{#if sdHeadendsError}
						<p class="hint error">{sdHeadendsError}</p>
					{/if}

					{#if sdHeadends.length > 0}
						<div class="sd-headends-results">
							{#each sdHeadends as headend (headend.headend)}
								{#each headend.lineups as lineup (lineup.lineup)}
									<div class="sd-headend-result-item">
										<span>{lineup.name} ({lineup.lineup})</span>
										<button
											type="button"
											class="save small"
											disabled={sdAddingLineupId === lineup.lineup}
											onclick={() => addSdLineup(lineup.lineup)}
										>
											{$_('network_settings.sd_add_lineup_button')}
										</button>
									</div>
								{/each}
							{/each}
						</div>
					{/if}
				</div>

				{#if sdError}
					<p class="hint error">{sdError}</p>
				{/if}

				<button class="save" disabled={sdSaving} onclick={saveSchedulesDirect}>
					{sdSaving ? $_('common.saving') : $_('common.save')}
				</button>
			</section>

			<section>
				<h3>{$_('network_settings.section_tmdb')}</h3>
				<p class="hint">{$_('network_settings.tmdb_hint')}</p>

				<label>
					{$_('network_settings.tmdb_api_key_label')}
					<input
						type="password"
						bind:value={tmdbApiKeyInput}
						placeholder={tmdbHasApiKey ? '(unchanged)' : ''}
					/>
				</label>

				<p class="hint">
					<a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noopener noreferrer">
						{$_('network_settings.tmdb_get_key_link')}
					</a>
				</p>

				{#if tmdbError}
					<p class="hint error">{tmdbError}</p>
				{/if}

				<button class="save" disabled={tmdbSaving} onclick={saveTmdb}>
					{tmdbSaving ? $_('common.saving') : $_('common.save')}
				</button>

				<p class="hint tmdb-attribution">{$_('network_settings.tmdb_attribution')}</p>
			</section>

			<section>
				<div class="section-header-row">
					<div>
						<h3>{$_('network_settings.guide_priority_heading')}</h3>
						<p class="hint">{$_('network_settings.guide_priority_hint')}</p>
					</div>
				</div>

				<div class="guide-priority-list">
					{#each guidePriorityList as providerId, index (providerId)}
						<div class="guide-priority-item">
							<div class="guide-priority-info">
								<span class="guide-priority-badge">{index + 1}</span>
								<div class="guide-priority-text">
									<span class="guide-priority-name">{providerLabel(providerId)}</span>
									<span class="guide-priority-sub">
										{#if providerId === 'xmltv'}
											{$_('network_settings.section_xmltv')}
										{:else if providerId === 'schedules_direct'}
											{$_('network_settings.section_schedules_direct')}
										{:else}
											{$_('network_settings.section_hdhomerun')}
										{/if}
									</span>
								</div>
							</div>
							<div class="guide-priority-actions">
								<button
									type="button"
									class="clear small"
									disabled={index === 0 || guidePrioritySaving}
									onclick={() => moveGuidePriorityUp(index)}
									aria-label={$_('network_settings.guide_priority_move_up')}
								>
									▲
								</button>
								<button
									type="button"
									class="clear small"
									disabled={index === guidePriorityList.length - 1 || guidePrioritySaving}
									onclick={() => moveGuidePriorityDown(index)}
									aria-label={$_('network_settings.guide_priority_move_down')}
								>
									▼
								</button>
							</div>
						</div>
					{/each}
				</div>

				{#if guidePriorityError}
					<p class="hint error">{guidePriorityError}</p>
				{/if}
				{#if guidePrioritySaved}
					<p class="hint ok">{$_('network_settings.guide_priority_saved')}</p>
				{/if}

				<button
					type="button"
					class="save"
					disabled={guidePrioritySaving}
					onclick={saveGuidePriority}
				>
					{guidePrioritySaving ? $_('network_settings.guide_priority_saving') : $_('network_settings.guide_priority_save')}
				</button>
			</section>

			<section>
				<div class="section-header-row">
					<div>
						<h3>{$_('network_settings.dvr_priority_heading')}</h3>
						<p class="hint">{$_('network_settings.dvr_priority_hint')}</p>
					</div>
				</div>

				<div class="guide-priority-list">
					{#each dvrPriorityList as serverId, index (serverId)}
						<div class="guide-priority-item">
							<div class="guide-priority-info">
								<span class="guide-priority-badge">{index + 1}</span>
								<div class="guide-priority-text">
									<span class="guide-priority-name">{dvrServerLabel(serverId)}</span>
									<span class="guide-priority-sub">
										{dvrServerDesc(serverId)}
									</span>
								</div>
							</div>
							<div class="guide-priority-actions">
								<button
									type="button"
									class="clear small"
									disabled={index === 0 || dvrPrioritySaving}
									onclick={() => moveDvrPriorityUp(index)}
									aria-label={$_('network_settings.dvr_priority_move_up')}
								>
									▲
								</button>
								<button
									type="button"
									class="clear small"
									disabled={index === dvrPriorityList.length - 1 || dvrPrioritySaving}
									onclick={() => moveDvrPriorityDown(index)}
									aria-label={$_('network_settings.dvr_priority_move_down')}
								>
									▼
								</button>
							</div>
						</div>
					{/each}
				</div>

				{#if dvrPriorityError}
					<p class="hint error">{dvrPriorityError}</p>
				{/if}
				{#if dvrPrioritySaved}
					<p class="hint ok">{$_('network_settings.dvr_priority_saved')}</p>
				{/if}

				<button
					type="button"
					class="save"
					disabled={dvrPrioritySaving}
					onclick={saveDvrPriority}
				>
					{dvrPrioritySaving ? $_('network_settings.dvr_priority_saving') : $_('network_settings.dvr_priority_save')}
				</button>
			</section>

			<section>
				<div class="section-header-row">
					<div>
						<h3>{$_('network_settings.channel_mapping_heading')}</h3>
						<p class="hint">{$_('network_settings.channel_mapping_hint')}</p>
					</div>
					<button
						type="button"
						class="test"
						disabled={guideRefreshing}
						onclick={handleRefreshGuide}
					>
						{guideRefreshing ? $_('network_settings.refreshing_guide') : $_('network_settings.refresh_guide')}
					</button>
				</div>

				{#if guideRefreshMessage}
					<p class="hint ok">{guideRefreshMessage}</p>
				{/if}
				{#if guideRefreshError}
					<p class="hint error">{guideRefreshError}</p>
				{/if}
				{#if channelSettingsError}
					<p class="hint error">{channelSettingsError}</p>
				{/if}

				{#if channelSettingsLoading && channelSettings.length === 0}
					<p class="hint">{$_('common.loading')}</p>
				{:else if channelSettings.length === 0}
					<p class="hint">{$_('network_settings.no_channels')}</p>
				{:else}
					{#if xmltvFeedChannels.length > 0}
						<datalist id="xmltv-feed-channels-list">
							{#each xmltvFeedChannels as feedCh (feedCh.xmltv_channel_id)}
								<option value={feedCh.xmltv_channel_id}>
									{feedCh.display_names.length > 0 ? feedCh.display_names.join(' / ') : feedCh.xmltv_channel_id}
								</option>
							{/each}
						</datalist>
					{/if}

					{#if sdStations.length > 0}
						<datalist id="sd-stations-list">
							{#each sdStations as st (st.station_id + st.lineup_id)}
								<option value={st.station_id}>
									{st.callsign ? `${st.callsign} (${st.name})` : st.name} - {st.channel_number || ''} [{st.lineup_id}]
								</option>
							{/each}
						</datalist>
					{/if}

					<div class="channel-settings-list">
						{#each channelSettings as channel (channel.id)}
							<div class="channel-setting-card">
								<div class="channel-header-row">
									<span class="channel-badge">{channel.channel_number}</span>
									<span class="channel-name">{channel.name}</span>
									{#if channel.is_hd}
										<span class="hd-badge">HD</span>
									{/if}
								</div>

								<div class="channel-fields-grid">
									<label>
										{$_('network_settings.guide_provider_label')}
										<select bind:value={channel.guide_provider}>
											<option value={null}>{$_('network_settings.guide_provider_default')}</option>
											<option value="hdhomerun_cloud">{$_('network_settings.guide_provider_hdhomerun')}</option>
											<option value="xmltv">{$_('network_settings.guide_provider_xmltv')}</option>
											<option value="schedules_direct">{$_('network_settings.guide_provider_schedules_direct')}</option>
										</select>
									</label>

									{#if channel.guide_provider === 'xmltv' || channel.guide_provider === null}
										<label>
											{$_('network_settings.xmltv_id_label')}
											<input
												type="text"
												list="xmltv-feed-channels-list"
												bind:value={channel.xmltv_channel_id}
												placeholder={$_('network_settings.xmltv_id_placeholder')}
											/>
										</label>

										<label>
											{$_('network_settings.xmltv_name_label')}
											<input
												type="text"
												bind:value={channel.xmltv_display_name}
												placeholder={$_('network_settings.xmltv_name_placeholder')}
											/>
										</label>
									{/if}

									{#if channel.guide_provider === 'schedules_direct' || channel.guide_provider === null}
										<label>
											{$_('network_settings.sd_station_id_label')}
											<input
												type="text"
												list="sd-stations-list"
												bind:value={channel.sd_station_id}
												placeholder={$_('network_settings.sd_station_id_placeholder')}
											/>
										</label>
									{/if}
								</div>

								<div class="channel-actions-row">
									<button
										type="button"
										class="save small"
										disabled={channelSavingId === channel.id}
										onclick={() => saveChannelSetting(channel)}
									>
										{channelSavingId === channel.id ? $_('common.saving') : $_('common.save')}
									</button>
									{#if channel.xmltv_channel_id}
										<button
											type="button"
											class="clear"
											disabled={channelSavingId === channel.id}
											onclick={() => clearXmltvMapping(channel)}
										>
											{$_('network_settings.clear_mapping')}
										</button>
									{/if}
									{#if channel.sd_station_id}
										<button
											type="button"
											class="clear"
											disabled={channelSavingId === channel.id}
											onclick={() => clearSdMapping(channel)}
										>
											{$_('network_settings.clear_sd_mapping')}
										</button>
									{/if}
									{#if channelSavedId === channel.id}
										<span class="hint ok">{$_('network_settings.channel_saved')}</span>
									{/if}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</section>

			<section>

				<h3>{$_('hdhomerun.detail.playback_heading')}</h3>
				<div class="auth-mode">
					<button
						type="button"
						class:active={playbackModeInput === 'server_transcode'}
						onclick={() => (playbackModeInput = 'server_transcode')}
					>
						{$_('hdhomerun.detail.mode_server_transcode')}
					</button>
					<button
						type="button"
						class:active={playbackModeInput === 'external'}
						onclick={() => (playbackModeInput = 'external')}
					>
						{$_('hdhomerun.detail.mode_external')}
					</button>
				</div>
				{#if playbackModeInput === 'server_transcode'}
					<p class="hint">{$_('hdhomerun.detail.server_transcode_hint')}</p>

					<label>
						{$_('hdhomerun.detail.transcode_hardware_label')}
						<select bind:value={hwaccelInput}>
							{#each transcodePresets as preset (preset.id)}
								<option value={preset.id}>{preset.label}</option>
							{/each}
						</select>
					</label>
					{#if selectedPreset}
						<p class="hint">{selectedPreset.description}</p>
					{/if}

					{#if hwaccelInput === 'custom'}
						<label>
							{$_('hdhomerun.detail.custom_ffmpeg_label')}
							<textarea bind:value={customFfmpegArgsInput} rows="2" placeholder="-c:v h264_v4l2m2m -b:v 4M -c:a aac"
							></textarea>
						</label>
					{/if}

					<label>
						{$_('hdhomerun.detail.hwaccel_device_label')}
						<input bind:value={hwaccelDeviceInput} placeholder="/dev/dri/renderD128" />
					</label>
					<p class="hint">{$_('hdhomerun.detail.hwaccel_device_hint')}</p>

					<label class="checkbox">
						<input type="checkbox" bind:checked={ffmpegDebugInput} />
						{$_('hdhomerun.detail.ffmpeg_debug_label')}
					</label>
					<p class="hint">{$_('hdhomerun.detail.ffmpeg_debug_hint')}</p>

					<label class="checkbox">
						<input type="checkbox" bind:checked={thumbnailsEnabledInput} />
						{$_('hdhomerun.detail.thumbnails_enabled_label')}
					</label>
					<p class="hint">{$_('hdhomerun.detail.thumbnails_enabled_hint')}</p>

					<p class="hint ffmpeg-command">
						<code>{livePreviewCommand}</code>
					</p>

					<div class="diagnostics">
						<h4>{$_('hdhomerun.detail.diagnostics_heading')}</h4>
						<p class="hint">{$_('hdhomerun.detail.diagnostics_hint')}</p>
						<button type="button" class="test" disabled={diagnosticsRunning} onclick={runDiagnostics}>
							{diagnosticsRunning ? $_('hdhomerun.detail.diagnostics_running') : $_('hdhomerun.detail.diagnostics_run')}
						</button>

						{#if diagnosticsError}
							<p class="hint error">{diagnosticsError}</p>
						{/if}

						{#if diagnostics}
							{#each diagnostics.summary as finding, index (index)}
								<p class="finding">{finding}</p>
							{/each}

							<h4>{$_('hdhomerun.detail.diagnostics_devices_heading')}</h4>
							{#if !diagnostics.dri.dir_exists}
								<p class="hint">{$_('hdhomerun.detail.diagnostics_no_dri')}</p>
							{:else if diagnostics.dri.devices.length === 0}
								<p class="hint">{$_('hdhomerun.detail.diagnostics_no_devices')}</p>
							{:else}
								<ul class="diagnostics-list">
									{#each diagnostics.dri.devices as device (device.path)}
										<li>
											<span class="status" class:ok={device.readable && device.writable}>
												{device.readable && device.writable ? '✓' : '✗'}
											</span>
											<code>{device.path}</code>
											<span class="muted">
												{device.error ?? `${device.mode} ${device.owner_uid}:${device.owner_gid}`}
											</span>
										</li>
									{/each}
								</ul>
							{/if}
							<p class="hint">
								{$_('hdhomerun.detail.diagnostics_process', {
									values: {
										uid: diagnostics.process.uid,
										gid: diagnostics.process.gid,
										groups: diagnostics.process.groups.join(', ') || '—',
									},
								})}
							</p>

							{#if diagnostics.vainfo}
								<h4>{$_('hdhomerun.detail.diagnostics_driver_heading')}</h4>
								<p class="hint">
									{diagnostics.vainfo.driver ?? $_('common.unknown')} ·
									{$_('hdhomerun.detail.diagnostics_h264_encode')}: {diagnostics.vainfo.can_encode_h264 ? '✓' : '✗'} ·
									{$_('hdhomerun.detail.diagnostics_mpeg2_decode')}: {diagnostics.vainfo.can_decode_mpeg2 ? '✓' : '✗'}
								</p>
								{#if !diagnostics.vainfo.ok}
									<pre class="diagnostics-output">{diagnostics.vainfo.output}</pre>
								{/if}
							{/if}

							<h4>{$_('hdhomerun.detail.diagnostics_presets_heading')}</h4>
							{#if diagnostics.sample_error}
								<p class="hint error">{diagnostics.sample_error}</p>
							{/if}
							<ul class="diagnostics-list">
								{#each Object.entries(diagnostics.probes) as [presetId, probe] (presetId)}
									<li>
										<span class="status" class:ok={probe.ok}>{probe.ok ? '✓' : '✗'}</span>
										<code>{presetId}</code>
										{#if !probe.ok}
											<pre class="diagnostics-output">{probe.output ||
													$_('hdhomerun.detail.diagnostics_no_output')}</pre>
										{/if}
									</li>
								{/each}
							</ul>
						{/if}
					</div>
				{:else}
					<p class="hint">{$_('hdhomerun.detail.external_only_hint')}</p>
				{/if}

				{#if playbackError}
					<p class="hint error">{playbackError}</p>
				{/if}
				{#if playbackSaved}
					<p class="hint">{$_('common.saved')}</p>
				{/if}

				<button class="save" disabled={playbackSaving} onclick={savePlayback}>
					{playbackSaving ? $_('common.saving') : $_('hdhomerun.detail.save_playback_settings')}
				</button>
			</section>
		</div>
	{/if}

	<div class="settings-group">
		<h2 class="group-title">{$_('settings.your_settings.title')}</h2>
		<p class="group-subtitle">{$_('settings.your_settings.subtitle')}</p>

		<section>
			<h3>{$_('settings.profile.heading')}</h3>
			<label>
				{$_('settings.profile.name_label')}
				<input type="text" bind:value={profileNameInput} maxlength="40" />
			</label>
			<label>
				{$_('settings.profile.avatar_label')}
				<input type="text" bind:value={profileAvatarInput} placeholder="🐱" maxlength="8" />
			</label>
			<label>
				{$_('settings.profile.pin_label')}
				<input
					type="password"
					inputmode="numeric"
					bind:value={profilePinInput}
					placeholder={profileHasPin ? $_('common.password_set_hint') : $_('settings.profile.pin_not_set')}
					maxlength="8"
				/>
			</label>
			{#if profileHasPin}
				<button class="clear" onclick={clearPin}>{$_('settings.profile.clear_pin')}</button>
			{/if}
			{#if profileError}
				<p class="hint error">{profileError}</p>
			{/if}
			{#if profileSaved}
				<p class="hint">{$_('common.saved')}</p>
			{/if}
			<button class="save" disabled={profileSaving || !profileNameInput.trim()} onclick={saveProfile}>
				{profileSaving ? $_('common.saving') : $_('settings.profile.save')}
			</button>

			{#if confirmingDeleteProfile}
				<p class="hint error">{$_('settings.profile.delete_confirm')}</p>
				<div class="confirm-actions">
					<button class="cancel" onclick={() => (confirmingDeleteProfile = false)} disabled={deletingProfile}>
						{$_('common.cancel')}
					</button>
					<button class="danger" onclick={deleteProfile} disabled={deletingProfile}>
						{deletingProfile ? $_('settings.profile.deleting') : $_('settings.profile.delete')}
					</button>
				</div>
			{:else}
				<button class="danger-link" onclick={() => (confirmingDeleteProfile = true)}
					>{$_('settings.profile.delete_link')}</button
				>
			{/if}
		</section>

		<section>
			<h3>{$_('settings.devices.heading')}</h3>

			{#if devicesError}
				<p class="hint error">{devicesError}</p>
			{/if}

			{#if devices.length > 0}
				<ul class="device-list">
					{#each devices as d (d.id)}
						<li>
							<span class="device-name">{d.name}</span>
							{#if d.id === $currentDevice?.id}
								<span class="device-actions">
									<span class="hint">({$_('settings.devices.this_device_label')})</span>
									<button type="button" class="link-button" onclick={() => (renamingDevice = true)}>
										{$_('settings.devices.rename')}
									</button>
								</span>
							{:else if confirmingForgetDeviceId === d.id}
								<span class="confirm-actions">
									<button
										class="cancel"
										onclick={() => (confirmingForgetDeviceId = null)}
										disabled={forgettingDeviceId === d.id}
									>
										{$_('common.cancel')}
									</button>
									<button class="danger" onclick={() => forgetDevice(d.id)} disabled={forgettingDeviceId === d.id}>
										{forgettingDeviceId === d.id ? $_('settings.devices.forgetting') : $_('settings.devices.forget')}
									</button>
								</span>
							{:else}
								<button class="danger-link" onclick={() => (confirmingForgetDeviceId = d.id)}
									>{$_('settings.devices.forget_device')}</button
								>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</section>

		{#if renamingDevice}
			<div class="rename-device-backdrop"></div>
			<div class="rename-device-dialog" bind:this={renameDialogEl} role="dialog" aria-label={$_('settings.devices.rename')}>
				<h4>{$_('settings.devices.rename')}</h4>
				<input type="text" bind:value={deviceNameInput} maxlength="40" />
				<div class="rename-device-actions">
					<button type="button" class="cancel" onclick={cancelRenameDevice}>
						{$_('common.cancel')}
					</button>
					<button class="save" disabled={savingDeviceName || !deviceNameInput.trim()} onclick={saveDeviceName}>
						{savingDeviceName ? $_('common.saving') : $_('common.save')}
					</button>
				</div>
			</div>
		{/if}

		<section>
			<h3>{$_('settings.language.title')}</h3>
			<select
				aria-label={$_('settings.language.title')}
				value={$locale}
				onchange={(e) => {
					locale.set(e.currentTarget.value);
					localeSaved = false;
				}}
			>
				<option value="en">English</option>
				<option value="es">Español</option>
				<option value="fr">Français</option>
				<option value="de">Deutsch</option>
			</select>

			{#if localeError}
				<p class="hint error">{localeError}</p>
			{/if}
			{#if localeSaved}
				<p class="hint">{$_('common.saved')}</p>
			{/if}
			<button class="save" disabled={localeSaving} onclick={saveLocale}>
				{localeSaving ? $_('common.saving') : $_('settings.language.save')}
			</button>
		</section>

		<section>
			<h3>{$_('settings.appearance.title')}</h3>
			<select
				aria-label={$_('settings.appearance.title')}
				value={$theme}
				onchange={(e) => {
					theme.set(e.currentTarget.value);
					themeSaved = false;
				}}
			>
				{#each themeIds as id (id)}
					<option value={id}>{themeNames[id] ?? id}</option>
				{/each}
			</select>

			{#if themeError}
				<p class="hint error">{themeError}</p>
			{/if}
			{#if themeSaved}
				<p class="hint">{$_('common.saved')}</p>
			{/if}
			<button class="save" disabled={themeSaving} onclick={saveTheme}>
				{themeSaving ? $_('common.saving') : $_('settings.appearance.save')}
			</button>
		</section>
	</div>
</div>

<style>
	.settings-page {
		padding: 2rem;
		min-height: 100vh;
		max-width: 30rem;
	}

	.back {
		background: none;
		border: none;
		font-size: 1.1rem;
		color: var(--color-accent);
		margin-bottom: 1.5rem;
		cursor: pointer;
		padding: 0.5rem 0;
	}

	h1 {
		margin: 0 0 1.5rem;
	}

	section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		margin-bottom: 1.5rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.75rem;
		padding: 1rem;
	}

	section h3 {
		margin: 0;
		font-size: 1rem;
	}

	section h4 {
		margin: 0.5rem 0 0;
		font-size: 0.9rem;
	}

	section h4:first-of-type {
		margin-top: 0;
	}

	.optional {
		font-weight: normal;
		color: var(--color-text-muted);
		font-size: 0.85rem;
	}

	.test-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.test {
		align-self: flex-start;
		background: none;
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.5rem 1rem;
		color: var(--color-accent);
		cursor: pointer;
	}

	.test-result {
		font-size: 0.85rem;
	}

	.test-result.ok {
		color: var(--color-success);
	}

	.test-result.fail {
		color: var(--color-error);
	}

	.settings-group {
		margin-bottom: 2rem;
	}

	.group-title {
		margin: 0 0 0.25rem;
		font-size: 1.2rem;
	}

	.group-subtitle {
		margin: 0 0 1rem;
		color: var(--color-text-muted);
		font-size: 0.85rem;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: 0.9rem;
		color: var(--color-text-muted);
	}

	input,
	select,
	textarea {
		font: inherit;
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-text);
	}

	textarea {
		font-family: var(--font-mono, monospace);
		font-size: 0.85rem;
		resize: vertical;
	}

	label.checkbox {
		flex-direction: row;
		align-items: center;
		gap: 0.5rem;
	}

	.auth-mode {
		display: flex;
		gap: 0.5rem;
	}

	.auth-mode button {
		flex: 1;
		background: none;
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.5rem;
		font-size: 0.85rem;
		color: var(--color-text-muted);
		cursor: pointer;
	}

	.auth-mode button.active {
		border-color: var(--color-accent);
		color: var(--color-accent);
	}

	.diagnostics {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		border-top: 1px solid var(--color-border);
		padding-top: 0.75rem;
		margin-top: 0.5rem;
	}

	.diagnostics h4 {
		margin: 0.5rem 0 0;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.finding {
		margin: 0;
		font-size: 0.85rem;
	}

	.diagnostics-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		font-size: 0.85rem;
	}

	.diagnostics-list .status {
		color: var(--color-danger, #e05a5a);
		margin-right: 0.4rem;
	}

	.diagnostics-list .status.ok {
		color: var(--color-success, #4caf50);
	}

	.diagnostics-list .muted {
		color: var(--color-text-muted);
		margin-left: 0.4rem;
	}

	.diagnostics-output {
		margin: 0.25rem 0 0;
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		font-family: var(--font-mono, monospace);
		font-size: 0.75rem;
		max-height: 12rem;
		overflow: auto;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}

	.ffmpeg-command {
		margin: 0;
	}

	.ffmpeg-command code {
		display: block;
		overflow-x: auto;
		white-space: pre;
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		font-size: 0.8rem;
	}

	.clear {
		align-self: flex-start;
		background: none;
		border: none;
		color: var(--color-text-muted);
		text-decoration: underline;
		cursor: pointer;
		padding: 0;
		font-size: 0.85rem;
	}

	.save {
		align-self: flex-start;
		background: var(--color-accent);
		color: var(--color-surface);
		border: none;
		border-radius: 0.5rem;
		padding: 0.5rem 1rem;
		cursor: pointer;
	}

	.save:disabled,
	.danger:disabled {
		opacity: 0.5;
		cursor: default;
	}

	.danger-link {
		align-self: flex-start;
		background: none;
		border: none;
		color: var(--color-error);
		text-decoration: underline;
		cursor: pointer;
		padding: 0;
		font-size: 0.85rem;
	}

	.confirm-actions {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.confirm-actions .cancel {
		background: none;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0;
		font-size: 0.85rem;
	}

	.danger {
		background: var(--color-error);
		color: var(--color-surface);
		border: none;
		border-radius: 0.5rem;
		padding: 0.4rem 0.75rem;
		cursor: pointer;
		font-size: 0.85rem;
	}

	.device-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.device-list li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.device-name {
		font-size: 0.9rem;
	}

	.device-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.link-button {
		background: none;
		border: none;
		color: var(--color-accent);
		text-decoration: underline;
		cursor: pointer;
		padding: 0;
		font-size: 0.85rem;
	}

	.rename-device-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		z-index: 100;
	}

	.rename-device-dialog {
		position: fixed;
		z-index: 101;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: 20rem;
		max-width: calc(100vw - 3rem);
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 1rem;
		padding: 1.5rem;
	}

	.rename-device-dialog h4 {
		margin: 0;
	}

	.rename-device-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
	}

	.rename-device-actions .cancel {
		background: none;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0.5rem 0.75rem;
		font-size: 0.9rem;
	}

	.member-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.member-list li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.member-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.avatar-sm {
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 50%;
		background: var(--color-surface-hover, var(--color-border));
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1rem;
	}

	.member-name {
		font-size: 0.9rem;
	}

	.role-badge {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--color-text-muted);
		border: 1px solid var(--color-border);
		border-radius: 999px;
		padding: 0.1rem 0.5rem;
	}

	.role-badge.admin {
		color: var(--color-accent);
		border-color: var(--color-accent);
	}

	.member-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.hint {
		color: var(--color-text-muted);
		margin: 0.25rem 0 0;
	}

	.hint.error {
		color: var(--color-error);
	}

	.hint.ok {
		color: var(--color-success, #4caf50);
	}

	.section-header-row {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.channel-settings-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		margin-top: 0.5rem;
	}

	.channel-setting-card {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.75rem;
	}

	.channel-header-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.channel-badge {
		font-weight: 700;
		color: var(--color-accent);
		font-size: 0.95rem;
	}

	.channel-name {
		font-weight: 600;
		font-size: 0.9rem;
	}

	.hd-badge {
		font-size: 0.7rem;
		background: var(--color-border);
		color: var(--color-text-muted);
		border-radius: 0.25rem;
		padding: 0.1rem 0.35rem;
		font-weight: 600;
	}

	.channel-fields-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.5rem;
	}

	@media (min-width: 600px) {
		.channel-fields-grid {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.channel-fields-grid label {
		min-width: 0;
	}

	.channel-fields-grid input,
	.channel-fields-grid select {
		width: 100%;
		min-width: 0;
	}

	.channel-actions-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 0.25rem;
	}

	.save.small {
		padding: 0.35rem 0.75rem;
		font-size: 0.85rem;
	}

	.sd-lineups-container,
	.sd-search-headends-container {
		margin-top: 0.75rem;
		padding: 0.5rem 0;
		border-top: 1px solid var(--color-border);
	}

	.sd-lineups-container h4,
	.sd-search-headends-container h4 {
		margin: 0 0 0.5rem;
		font-size: 0.9rem;
		font-weight: 600;
	}

	.sd-lineups-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.sd-lineup-item,
	.sd-headend-result-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.35rem 0.5rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.35rem;
		font-size: 0.85rem;
	}

	.sd-search-row {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.sd-headends-results {
		margin-top: 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.guide-priority-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin: 0.5rem 0;
	}

	.guide-priority-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.5rem 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		gap: 1rem;
	}

	.guide-priority-info {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.guide-priority-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		background: var(--color-accent);
		color: var(--color-surface);
		font-weight: 700;
		font-size: 0.8rem;
		flex-shrink: 0;
	}

	.guide-priority-text {
		display: flex;
		flex-direction: column;
	}

	.guide-priority-name {
		font-weight: 600;
		font-size: 0.9rem;
	}

	.guide-priority-sub {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.guide-priority-actions {
		display: flex;
		gap: 0.25rem;
	}

	.stats-panel {
		margin-top: 1rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.stats-panel h4 {
		margin: 0;
		font-size: 0.9rem;
		color: var(--color-text);
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
		gap: 0.75rem;
	}

	.stat-card {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
	}

	.stat-label {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.stat-value {
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--color-text);
		word-break: break-word;
	}
</style>

