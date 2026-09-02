// Dynamic (not static) so the API base URL can be set as a runtime
// environment variable against the built Node server, rather than baked
// into the client bundle at Docker build time — lets frontend and backend
// run on different hosts without a rebuild.
import { env } from '$env/dynamic/public';
import { logger } from '$lib/logger';

export interface AppSettings {
	timezone: string;
	guide_provider_priority: string;
	dvr_server_priority: string;
}

export interface HDHomeRunGuideEntry {
	series_id?: string | null;
	title: string;
	episode_title: string | null;
	episode_number?: string | null;
	season_number?: number | null;
	synopsis?: string | null;
	start: number | null;
	end: number | null;
	original_airdate?: number | string | null;
	image_url?: string | null;
	channel_number?: string;
	category?: string | null;
	is_new?: boolean | null;
	audio?: string | null;
	has_cc?: boolean | null;
	is_hd?: boolean | null;
}

export interface HDHomeRunRecordingRule {
	RecordingRuleID: string;
	SeriesID: string;
	Title: string;
	Synopsis?: string;
	ImageURL?: string;
	ChannelOnly?: string;
	DateTimeOnly?: number;
	Priority?: number;
	StartPadding?: number;
	EndPadding?: number;
	RecentOnly?: number | boolean;
	MaxEpisodesToKeep?: number | null;
	TitleMatchMode?: 'exact' | 'contains';
	KeywordQuery?: string | null;
	Provider?: 'builtin' | 'hdhomerun';
	provider?: 'builtin' | 'hdhomerun';
}

export interface RecordingRuleOptions {
	startPadding?: number;
	endPadding?: number;
	recentOnly?: boolean;
	maxEpisodesToKeep?: number;
	server?: 'builtin' | 'hdhomerun';
	title?: string;
	titleMatchMode?: 'exact' | 'contains';
	keywordQuery?: string;
	channel?: string;
}

export interface HDHomeRunFullGuideChannel {
	channel_number: string;
	channel_name: string;
	airings: HDHomeRunGuideEntry[];
}

export interface HDHomeRunTunerInfo {
	friendly_name: string;
	model_number: string | null;
	firmware_version: string | null;
	tuner_count: number | null;
}

export interface HDHomeRunDvrInfo {
	friendly_name: string;
	version: string | null;
	free_space_bytes: number | null;
	is_builtin?: boolean;
}

export interface HDHomeRunChannel {
	channel_number: string;
	name: string;
	is_hd: boolean;
	is_drm: boolean;
	stream_url: string;
	playback_url: string | null;
	now: HDHomeRunGuideEntry | null;
	next: HDHomeRunGuideEntry | null;
}

export interface TunerViewerInfo {
	user_name: string;
	client_ip: string | null;
}

export interface TunerClientInfo {
	type: 'scheduled_recording' | 'live_watch' | 'external' | 'direct_stream' | 'idle';
	name: string;
	ip: string | null;
	hostname: string | null;
	details: string;
	recording_id: string | null;
	scheduled_id: string | null;
	is_recording: boolean;
	viewers: TunerViewerInfo[];
}

export interface TunerWarningInfo {
	severity: 'warning' | 'danger' | 'info';
	message: string;
}

export interface HDHomeRunTuner {
	index: number;
	resource?: string;
	in_use: boolean;
	channel_number: string | null;
	channel_name: string | null;
	target_ip?: string | null;
	client?: TunerClientInfo | null;
	warning?: TunerWarningInfo | null;
	signal_strength_percent: number | null;
	signal_quality_percent: number | null;
	symbol_quality_percent: number | null;
	network_rate_bps: number | null;
}

/** GET /api/guide/channels — see backend/app/api/guide.py. */
export interface HDHomeRunChannelsResponse {
	channels: HDHomeRunChannel[];
	guide_available: boolean;
}

export interface HDHomeRunChannelSetting {
	id: string;
	channel_number: string;
	name: string;
	is_hd: boolean;
	is_favorite: boolean;
	hidden: boolean;
	guide_provider: 'hdhomerun_cloud' | 'xmltv' | 'schedules_direct' | null;
	xmltv_channel_id: string | null;
	xmltv_display_name: string | null;
	sd_station_id: string | null;
	sd_lineup_id: string | null;
}

export interface XMLTVFeedChannel {
	xmltv_channel_id: string;
	display_names: string[];
}

export interface XMLTVStats {
	url: string | null;
	last_refreshed_at: string | null;
	channels_in_feed: number;
	mapped_channels_count: number;
	channels_with_programs: number;
	programs_count: number;
	days_count: number;
	start_date: string | null;
	end_date: string | null;
	start_ts: number | null;
	end_ts: number | null;
}

export interface SchedulesDirectLineup {
	lineup: string;
	name: string;
	transport?: string;
	location?: string;
	uri?: string;
}

export interface SchedulesDirectHeadend {
	headend: string;
	lineups: SchedulesDirectLineup[];
	transport?: string;
	location?: string;
}

export interface SchedulesDirectStation {
	station_id: string;
	lineup_id: string;
	lineup_name?: string;
	channel_number?: string;
	name: string;
	callsign?: string;
}

export interface SchedulesDirectTestResult {
	ok: boolean;
	detail: {
		expires?: string;
		max_lineups?: number;
		lineups?: SchedulesDirectLineup[];
	} | null;
	error: string | null;
}


export interface HDHomeRunRecording {
	recording_id?: string | null;
	// Only present in the response of POST /api/watch/{channel}/start —
	// identifies this viewer's watch-session lifecycle (heartbeat/stop/
	// promote), distinct from recording_id which identifies the shared
	// capture that other viewers/schedules may also be attached to.
	session_id?: string | null;
	series_id?: string | null;
	title: string;
	episode_title?: string | null;
	season_number?: number | null;
	episode_number?: string | null;
	synopsis?: string | null;
	channel_number?: string | null;
	channel_name: string | null;
	start: number | null;
	record_end: number | null;
	play_url?: string | null;
	image_url?: string | null;
	duration_seconds?: number | null;
	file_size_bytes?: number | null;
	has_captions?: boolean;
	video_codec?: string | null;
	video_width?: number | null;
	video_height?: number | null;
	audio_codec?: string | null;
	audio_channels?: number | null;
	original_air_date?: string | null;
	category?: string | null;
	category_type?: 'shows' | 'movies' | 'sports';
	is_dvr_file?: boolean;
	provider?: 'builtin' | 'hdhomerun';
}

export interface HDHomeRunRecordingVideoInfo {
	codec: string | null;
	width: number | null;
	height: number | null;
	fps: number | null;
}

export interface HDHomeRunRecordingAudioInfo {
	index: number;
	codec: string | null;
	channels: number | null;
	language: string | null;
}

/** What /recording-stream will actually do for playback, per current settings. */
export interface HDHomeRunTranscodeInfo {
	transcoding: boolean;
	preset: string | null;
	preset_label: string | null;
	hardware: boolean;
}

/** GET /api/dvr/recording-detail — see backend/app/api/dvr.py. */
export interface HDHomeRunRecordingDetail {
	is_in_progress: boolean;
	duration_seconds: number | null;
	video: HDHomeRunRecordingVideoInfo | null;
	audio: HDHomeRunRecordingAudioInfo[];
	has_captions: boolean;
	transcode: HDHomeRunTranscodeInfo;
}

export interface HDHomeRunTranscodePreset {
	id: string;
	label: string;
	description: string;
	input_args: string[];
	output_args: string[];
	hardware: boolean;
}

export interface HWAccelDevice {
	path: string;
	mode?: string;
	owner_uid?: number;
	owner_gid?: number;
	readable?: boolean;
	writable?: boolean;
	error?: string;
}

export interface HWAccelProbe {
	ok: boolean;
	command: string | null;
	exit_code: number | null;
	output: string;
}

/** Report from GET /api/streaming/hwaccel-diagnostics — see backend/app/hwaccel.py. */
export interface HWAccelDiagnostics {
	device: string;
	process: { uid: number; gid: number; groups: number[] };
	dri: { dir_exists: boolean; devices: HWAccelDevice[] };
	ffmpeg: {
		version: string;
		hwaccels: string[];
		hardware_encoders: string[];
		ffmpeg_available: boolean;
	};
	vainfo: {
		ok: boolean;
		output: string;
		driver: string | null;
		profiles: Record<string, string[]>;
		can_decode_mpeg2: boolean;
		can_encode_h264: boolean;
	} | null;
	probes: Record<string, HWAccelProbe>;
	sample_error: string | null;
	summary: string[];
}

// Network-level integration settings (HDHomeRun, Schedules Direct, XMLTV) —
// shared per-device connection config edited once, not per widget instance.
// See backend/app/api/network_settings.py.
export interface NetworkIntegration {
	id: string;
	type: string;
	name: string;
	settings: Record<string, unknown>;
}

export interface NetworkTestConnectionResult {
	ok: boolean;
	detail: string | null;
	error: string | null;
}

export interface UserProfile {
	id: string;
	name: string;
	avatar: string | null;
	has_pin: boolean;
}

export type UserRole = 'admin' | 'member';

export interface CurrentUser {
	id: string;
	name: string;
	avatar: string | null;
	role: UserRole;
}

export interface UserPreferences {
	theme: string;
	voice_provider: string;
	voice_id: string;
	voice_name: string;
	locale: string;
}

export interface SetupStatus {
	needs_setup: boolean;
}

export interface HouseholdUser {
	id: string;
	name: string;
	avatar: string | null;
	has_pin: boolean;
	role: UserRole;
	created_at: string;
}

export interface JobRun {
	id: string;
	job_id: string;
	status: 'running' | 'success' | 'failed';
	started_at: string;
	finished_at: string | null;
	error: string | null;
}

export interface AdminJob {
	id: string;
	name: string;
	description: string;
	trigger: 'interval' | 'event';
	recent_runs: JobRun[];
}

// fetch() itself throws a TypeError before ever reaching a response — that's
// the one reliable signal that the request never made it to the server (CORS
// block, DNS failure, connection refused), as opposed to a server response
// that just wasn't `ok`. Used to tell "backend unreachable" apart from
// "backend responded with an error" in first-run/login error messaging.
export type FetchErrorKind = 'network' | 'server';

export function describeFetchError(error: unknown): FetchErrorKind {
	return error instanceof TypeError ? 'network' : 'server';
}

// `credentials: 'include'` on every request so the session cookie
// (set by the backend as httponly, so JS can't attach it manually) round-trips
// even when the frontend and backend are on different ports/origins.
async function getJSON<T>(path: string): Promise<T> {
	const response = await fetch(`${env.PUBLIC_API_BASE_URL}${path}`, { credentials: 'include' });
	if (!response.ok) {
		const message = await _errorMessage(path, response);
		logger.warn(`Request to ${path} failed: ${response.status}`);
		throw new Error(message);
	}
	return response.json();
}

async function patchJSON<T>(path: string, body: Record<string, unknown>): Promise<T> {
	const response = await fetch(`${env.PUBLIC_API_BASE_URL}${path}`, {
		method: 'PATCH',
		credentials: 'include',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body),
	});
	if (!response.ok) {
		const message = await _errorMessage(path, response);
		logger.warn(`Request to ${path} failed: ${response.status}`);
		throw new Error(message);
	}
	return response.json();
}

// Reads a failed response's `{detail: string}` body (FastAPI's HTTPException
// shape), if present, so callers can surface the server's actual reason
// (e.g. why an HDHomeRun DVR recording rule was rejected) instead of just a
// bare status code. Falls back to the status-only message when the body
// isn't JSON or has no `detail`.
async function _errorMessage(path: string, response: Response): Promise<string> {
	try {
		const body = await response.json();
		if (body && typeof body.detail === 'string' && body.detail) {
			return body.detail;
		}
	} catch {
		// Not JSON, or already consumed — fall through to the generic message.
	}
	return `Request to ${path} failed: ${response.status}`;
}

async function postJSON<T>(path: string, body?: Record<string, unknown>): Promise<T> {
	const response = await fetch(`${env.PUBLIC_API_BASE_URL}${path}`, {
		method: 'POST',
		credentials: 'include',
		...(body !== undefined && {
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body),
		}),
	});
	if (!response.ok) {
		const message = await _errorMessage(path, response);
		logger.warn(`Request to ${path} failed: ${response.status}`);
		throw new Error(message);
	}
	return response.json();
}

async function deleteJSON<T>(path: string): Promise<T> {
	const response = await fetch(`${env.PUBLIC_API_BASE_URL}${path}`, {
		method: 'DELETE',
		credentials: 'include',
	});
	if (!response.ok) {
		const message = await _errorMessage(path, response);
		logger.warn(`Request to ${path} failed: ${response.status}`);
		throw new Error(message);
	}
	return response.json();
}

export const api = {
	themes: () => getJSON<{ themes: { id: string; name: string }[]; default: string }>('/api/theme'),
	settings: () => getJSON<AppSettings>('/api/settings'),
	updateSettings: (partial: Record<string, string>) => patchJSON<AppSettings>('/api/settings', partial),
	hdhomerunTranscodePresets: () => getJSON<HDHomeRunTranscodePreset[]>('/api/streaming/transcode-presets'),
	// Channel playback_url is a backend-relative proxy path — resolve it
	// against the API base the same way other stream URLs do.
	hdhomerunPlaybackUrl: (url: string) => (url.startsWith('/') ? `${env.PUBLIC_API_BASE_URL}${url}` : url),
	hdhomerunRecordingStreamUrl: (
		playUrl: string,
		options?: { start?: number; audioIndex?: number; recordingId?: string | null },
	) => {
		const params = new URLSearchParams({ url: playUrl });
		if (options?.start !== undefined) params.set('start', String(options.start));
		if (options?.audioIndex !== undefined) params.set('audio_index', String(options.audioIndex));
		if (options?.recordingId) params.set('recording_id', options.recordingId);
		return `${env.PUBLIC_API_BASE_URL}/api/dvr/recording-stream?${params.toString()}`;
	},
	hdhomerunRecordingDetail: (options: {
		url: string;
		recordingId: string;
		start?: number | null;
		recordEnd?: number | null;
	}) => {
		const params = new URLSearchParams({ url: options.url, recording_id: options.recordingId });
		if (options.start !== undefined && options.start !== null) params.set('start', String(options.start));
		if (options.recordEnd !== undefined && options.recordEnd !== null) {
			params.set('record_end', String(options.recordEnd));
		}
		return getJSON<HDHomeRunRecordingDetail>(`/api/dvr/recording-detail?${params.toString()}`);
	},
	hdhomerunRecordingCaptionsUrl: (options: { url: string; recordingId: string; recordEnd?: number | null }) => {
		const params = new URLSearchParams({ url: options.url, recording_id: options.recordingId });
		if (options.recordEnd !== undefined && options.recordEnd !== null) {
			params.set('record_end', String(options.recordEnd));
		}
		return `${env.PUBLIC_API_BASE_URL}/api/dvr/recording-captions.vtt?${params.toString()}`;
	},
	hdhomerunRecordingThumbnailSpriteUrl: (options: {
		url: string;
		recordingId: string;
		recordEnd?: number | null;
	}) => {
		const params = new URLSearchParams({ url: options.url });
		if (options.recordEnd !== undefined && options.recordEnd !== null) {
			params.set('record_end', String(options.recordEnd));
		}
		return `${env.PUBLIC_API_BASE_URL}/api/dvr/recording-thumbnails/${options.recordingId}.jpg?${params.toString()}`;
	},
	hdhomerunRecordingThumbnailVttUrl: (options: { url: string; recordingId: string; recordEnd?: number | null }) => {
		const params = new URLSearchParams({ url: options.url });
		if (options.recordEnd !== undefined && options.recordEnd !== null) {
			params.set('record_end', String(options.recordEnd));
		}
		return `${env.PUBLIC_API_BASE_URL}/api/dvr/recording-thumbnails/${options.recordingId}.vtt?${params.toString()}`;
	},
	hdhomerunPlaylistUrl: (channelNumber: string) =>
		`${env.PUBLIC_API_BASE_URL}/api/streaming/playlist/${channelNumber}`,
	// Admin-only, and slow by design: it test-encodes a short clip through
	// each plausible preset, so budget several seconds.
	hdhomerunHwaccelDiagnostics: (device?: string) =>
		getJSON<HWAccelDiagnostics>(
			`/api/streaming/hwaccel-diagnostics${device ? `?device=${encodeURIComponent(device)}` : ''}`,
		),
	addHDHomeRunRecordingRule: (rule: {
		series_id?: string;
		date_time?: number;
		channel?: string;
		recent_only?: boolean;
		start_padding?: number;
		end_padding?: number;
		max_episodes_to_keep?: number;
		server?: 'builtin' | 'hdhomerun';
		title?: string;
		title_match_mode?: 'exact' | 'contains';
		keyword_query?: string;
	}) => postJSON<HDHomeRunRecordingRule[]>('/api/dvr/recording-rules', rule),
	deleteHDHomeRunRecordingRule: (ruleId: string) =>
		deleteJSON<HDHomeRunRecordingRule[]>(`/api/dvr/recording-rules/${ruleId}`),
	deleteRecording: (recordingId: string) => deleteJSON<{ status: string }>(`/api/dvr/recordings/${recordingId}`),
	getHDHomeRunGuide: (start?: number, end?: number) => {
		const params = new URLSearchParams();
		if (start !== undefined) params.set('start', String(start));
		if (end !== undefined) params.set('end', String(end));
		const query = params.toString();
		return getJSON<HDHomeRunFullGuideChannel[]>(`/api/guide${query ? `?${query}` : ''}`);
	},
	getHDHomeRunChannels: () => getJSON<HDHomeRunChannelsResponse>('/api/guide/channels'),
	getDvrInfo: () => getJSON<HDHomeRunDvrInfo>('/api/dvr/info'),
	listRecordings: () => getJSON<HDHomeRunRecording[]>('/api/dvr/recordings'),
	listRecordingRules: () => getJSON<HDHomeRunRecordingRule[]>('/api/dvr/recording-rules'),
	getTunerStatus: () => getJSON<HDHomeRunTuner[]>('/api/tuner/status'),
	getTunerInfo: () => getJSON<HDHomeRunTunerInfo>('/api/tuner/info'),
	terminateTuner: (index: number) =>
		postJSON<{ ok: boolean; message: string; tuners: HDHomeRunTuner[] }>(`/api/tuner/${index}/terminate`),
	listNetworkIntegrations: () => getJSON<NetworkIntegration[]>('/api/network-settings'),
	getNetworkIntegration: (type: string) => getJSON<NetworkIntegration>(`/api/network-settings/${type}`),
	updateNetworkIntegration: (type: string, settings: Record<string, unknown>) =>
		patchJSON<NetworkIntegration>(`/api/network-settings/${type}`, settings),
	testHDHomeRunTunerConnection: (settings: Record<string, unknown>) =>
		postJSON<NetworkTestConnectionResult>('/api/network-settings/hdhomerun/test-tuner-connection', settings),
	testHDHomeRunDvrConnection: (settings: Record<string, unknown>) =>
		postJSON<NetworkTestConnectionResult>('/api/network-settings/hdhomerun/test-dvr-connection', settings),
	testHDHomeRunSshConnection: (settings: Record<string, unknown>) =>
		postJSON<NetworkTestConnectionResult>('/api/network-settings/hdhomerun/test-ssh-connection', settings),
	testSchedulesDirectConnection: (settings: Record<string, unknown>) =>
		postJSON<SchedulesDirectTestResult>('/api/network-settings/schedules-direct/test-connection', settings),
	getSchedulesDirectLineups: () => getJSON<SchedulesDirectLineup[]>('/api/network-settings/schedules-direct/lineups'),
	getSchedulesDirectHeadends: (postalCode: string, country = 'USA') =>
		getJSON<SchedulesDirectHeadend[]>(
			`/api/network-settings/schedules-direct/headends?postal_code=${encodeURIComponent(postalCode)}&country=${encodeURIComponent(country)}`
		),
	addSchedulesDirectLineup: (lineupId: string) =>
		postJSON<{ code?: number; message?: string }>(`/api/network-settings/schedules-direct/lineups/${encodeURIComponent(lineupId)}`),
	deleteSchedulesDirectLineup: (lineupId: string) =>
		deleteJSON<{ code?: number; message?: string }>(`/api/network-settings/schedules-direct/lineups/${encodeURIComponent(lineupId)}`),
	listUsers: () => getJSON<UserProfile[]>('/api/users'),
	createUser: (name: string, avatar?: string, pin?: string) =>
		postJSON<CurrentUser>('/api/users', {
			name,
			...(avatar !== undefined && { avatar }),
			...(pin !== undefined && { pin }),
		}),
	loginUser: (id: string, pin?: string) => postJSON<CurrentUser>(`/api/users/${id}/login`, { pin }),
	logoutUser: () => postJSON<{ status: string }>('/api/users/logout'),
	currentUser: () => getJSON<CurrentUser>('/api/users/me'),
	updateUser: (partial: { name?: string; avatar?: string; pin?: string }) =>
		patchJSON<CurrentUser>('/api/users/me', partial),
	deleteUser: () => deleteJSON<{ status: string }>('/api/users/me'),
	getPreferences: () => getJSON<UserPreferences>('/api/users/me/preferences'),
	updatePreferences: (partial: Partial<UserPreferences>) =>
		patchJSON<UserPreferences>('/api/users/me/preferences', partial),
	setupStatus: () => getJSON<SetupStatus>('/api/setup/status'),
	createSetupAdmin: (name: string, avatar?: string, pin?: string) =>
		postJSON<CurrentUser>('/api/setup/admin', {
			name,
			...(avatar !== undefined && { avatar }),
			...(pin !== undefined && { pin }),
		}),
	listHouseholdUsers: () => getJSON<HouseholdUser[]>('/api/admin/users'),
	updateUserRole: (id: string, role: UserRole) => patchJSON<HouseholdUser>(`/api/admin/users/${id}/role`, { role }),
	removeHouseholdUser: (id: string) => deleteJSON<{ status: string }>(`/api/admin/users/${id}`),
	listJobs: () => getJSON<AdminJob[]>('/api/admin/jobs'),
	triggerJob: (id: string) => postJSON<{ status: string }>(`/api/admin/jobs/${id}/run`),
	getChannelSettings: () => getJSON<HDHomeRunChannelSetting[]>('/api/guide/channels/settings'),
	updateChannelSetting: (
		channelId: string,
		payload: {
			guide_provider?: 'hdhomerun_cloud' | 'xmltv' | 'schedules_direct' | null;
			xmltv_channel_id?: string | null;
			xmltv_display_name?: string | null;
			sd_station_id?: string | null;
			sd_lineup_id?: string | null;
			is_favorite?: boolean;
			hidden?: boolean;
		}
	) => patchJSON<HDHomeRunChannelSetting>(`/api/guide/channels/${channelId}`, payload as Record<string, unknown>),
	getXmltvFeedChannels: () => getJSON<XMLTVFeedChannel[]>('/api/guide/xmltv-feed-channels'),
	getXmltvStats: () => getJSON<XMLTVStats>('/api/guide/xmltv/stats'),
	reloadXmltvGuide: () => postJSON<{ ok: boolean; stats: XMLTVStats; message: string }>('/api/guide/xmltv/reload'),
	getSchedulesDirectStations: () => getJSON<SchedulesDirectStation[]>('/api/guide/schedules-direct-stations'),
	refreshGuide: () => postJSON<{ status: string; message: string }>('/api/guide/refresh'),
	// Auto-starts (or attaches to an already-running) hidden recording behind
	// a live channel so the player can reuse the in-progress-recording
	// playback path (pause/rewind). Returns recording_id: null when no tuner
	// is free and no capture already exists — caller falls back to plain live
	// streaming. session_id identifies this viewer's own lifecycle for
	// heartbeat/stop/promote, distinct from the shared recording_id. See
	// backend/app/api/watch.py.
	startWatch: (channelNumber: string) =>
		postJSON<HDHomeRunRecording | { recording_id: null; session_id: null }>(`/api/watch/${channelNumber}/start`),
	heartbeatWatch: (sessionId: string) => postJSON<void>(`/api/watch/${sessionId}/heartbeat`),
	promoteWatch: (
		sessionId: string,
		options?: {
			title?: string;
			episode_title?: string;
			season_number?: number;
			episode_number?: number;
			synopsis?: string;
			image_url?: string;
			original_air_date?: string;
			category?: string;
			end_ts?: number;
		},
	) => postJSON<HDHomeRunRecording>(`/api/watch/${sessionId}/promote`, options ?? {}),
	// Raw fetch with keepalive (not postJSON) so this survives a tab close/
	// navigation that would otherwise cancel an in-flight request.
	stopWatch: (sessionId: string) => {
		fetch(`${env.PUBLIC_API_BASE_URL}/api/watch/${sessionId}/stop`, {
			method: 'POST',
			credentials: 'include',
			keepalive: true,
		}).catch(() => {
			// Best-effort: reap_stale_watches on the backend is the backstop.
		});
	},
};

