import { writable, get } from 'svelte/store';
import {
	api,
	type HDHomeRunChannel,
	type HDHomeRunGuideEntry,
	type HDHomeRunRecordingRule,
	type RecordingRuleOptions,
} from '$lib/api';
import { getActiveCastSessionId, endCastSession, setActiveCastSessionId } from '$lib/cast/cast-loader';
import {
	isKeepPlayingOnNavigateEnabled,
	setKeepPlayingOnNavigateEnabled,
} from '$lib/keep-playing-preference';
import {
	isAutoSkipCommercialsEnabled,
	setAutoSkipCommercialsEnabled,
} from '$lib/auto-skip-commercials-preference';
import { createWatchSessionHeartbeat } from './watchSessionHeartbeat';

export interface PlaybackMedia {
	title: string;
	url: string;
	playUrl?: string;
	provider?: 'builtin' | 'hdhomerun' | null;
	recordingId?: string | null;
	watchSessionId?: string | null;
	startTimestamp?: number | null;
	recordEndTimestamp?: number | null;
	seekable: boolean;
	isWatchSession?: boolean;
	channel?: HDHomeRunChannel | null;
	airing?: HDHomeRunGuideEntry | null;
}

// Page-owned contextual data/callbacks, published by whichever page started
// playback - never invented by the store itself.
export interface PlaybackContext {
	channels: HDHomeRunChannel[];
	favoriteChannels: Set<string>;
	recordingRules: HDHomeRunRecordingRule[];
	pendingRuleIds: Set<string>;
	officialDvrActive: boolean;
	recordingLoading: string | null;
	onRecordEpisode?: (
		seriesId?: string | null,
		channelNumber?: string | null,
		start?: number | null,
		options?: RecordingRuleOptions,
	) => Promise<void> | void;
	onRecordSeries?: (
		seriesId: string,
		channelNumber?: string | null,
		options?: RecordingRuleOptions,
	) => Promise<void> | void;
	onUpdateRule?: (
		ruleId: string,
		mode: 'episode' | 'series',
		options: RecordingRuleOptions,
	) => Promise<void> | void;
	onCancelRule?: (ruleId: string) => Promise<void> | void;
	onToggleFavorite?: (channelNumber: string) => Promise<void> | void;
	onChannelChange?: (channel: HDHomeRunChannel) => void;
	onToggleMultiView?: () => void;
}

interface PlaybackState {
	media: PlaybackMedia | null;
	originPath: string | null;
	context: PlaybackContext | null;
}

export const playback = writable<PlaybackState>({ media: null, originPath: null, context: null });

// Lets a page refresh reopen the player on the recording that was playing
// (HDHomeRunPlayer then resumes at the saved spot - see resume-position.ts).
// sessionStorage, so it's scoped to this tab: a new tab never pops a player
// open on its own. Only completed/seekable recordings qualify - live
// channels have no position to return to, and watch sessions are stopped
// server-side on pagehide.
const ACTIVE_PLAYBACK_KEY = 'hdhr_active_playback';

function isRestorable(media: PlaybackMedia): boolean {
	return media.seekable && !media.isWatchSession && Boolean(media.recordingId || media.playUrl);
}

function persistActivePlayback(media: PlaybackMedia | null, originPath: string | null): void {
	if (typeof sessionStorage === 'undefined') return;
	try {
		if (media && isRestorable(media)) {
			sessionStorage.setItem(ACTIVE_PLAYBACK_KEY, JSON.stringify({ media, originPath }));
		} else {
			sessionStorage.removeItem(ACTIVE_PLAYBACK_KEY);
		}
	} catch {
		// Ignore storage access errors in restricted contexts
	}
}

// A restored player has no page-owned context yet - an empty (non-null)
// one lets useOwnedPlaybackContext/updateContext fill in the real data and
// callbacks once the origin page mounts (updateContext ignores a null
// context).
function emptyContext(): PlaybackContext {
	return {
		channels: [],
		favoriteChannels: new Set(),
		recordingRules: [],
		pendingRuleIds: new Set(),
		officialDvrActive: false,
		recordingLoading: null,
	};
}

export function restoreActivePlayback(): void {
	if (typeof sessionStorage === 'undefined') return;
	try {
		const raw = sessionStorage.getItem(ACTIVE_PLAYBACK_KEY);
		if (!raw) return;
		const parsed = JSON.parse(raw) as { media?: PlaybackMedia; originPath?: string | null };
		const media = parsed?.media;
		if (!media || typeof media.url !== 'string' || typeof media.title !== 'string' || !isRestorable(media)) {
			sessionStorage.removeItem(ACTIVE_PLAYBACK_KEY);
			return;
		}
		playback.set({ media, originPath: parsed.originPath ?? null, context: emptyContext() });
	} catch {
		// Corrupt/inaccessible - just don't restore
	}
}

export const keepPlayingOnNavigate = writable<boolean>(isKeepPlayingOnNavigateEnabled());
export const autoSkipCommercials = writable<boolean>(isAutoSkipCommercialsEnabled());

// Only one session plays at a time here, so a single fixed key is enough to
// address it in the shared heartbeat tracker.
const HEARTBEAT_KEY = 'playback';
const heartbeat = createWatchSessionHeartbeat();

function stopCurrent() {
	const current = get(playback);
	heartbeat.stop(HEARTBEAT_KEY);
	if (current.media?.isWatchSession && current.media.watchSessionId) {
		api.stopWatch(current.media.watchSessionId);
	}
	const castSessionId = getActiveCastSessionId();
	if (castSessionId) {
		endCastSession();
		setActiveCastSessionId(null);
	}
}

export function startPlayback(media: PlaybackMedia, originPath: string, context: PlaybackContext): void {
	stopCurrent();
	playback.set({ media, originPath, context });
	persistActivePlayback(media, originPath);
	if (media.isWatchSession && media.watchSessionId) {
		heartbeat.start(HEARTBEAT_KEY, media.watchSessionId);
	}
}

export function updateContext(partial: Partial<PlaybackContext>): void {
	playback.update((state) => {
		if (!state.context) return state;
		return { ...state, context: { ...state.context, ...partial } };
	});
}

/**
 * Synchronizes page-owned playback context to the global playback store if
 * the current originPath matches the specified pathname.
 */
export function syncOwnedPlaybackContext(
	pathname: string | (() => string),
	buildContext: () => PlaybackContext,
): boolean {
	const current = get(playback);
	const targetPath = typeof pathname === 'function' ? pathname() : pathname;
	if (current.media && current.originPath === targetPath) {
		updateContext(buildContext());
		return true;
	}
	return false;
}

export { useOwnedPlaybackContext } from './use-owned-playback-context.svelte';

export function stopPlayback(): void {
	stopCurrent();
	playback.set({ media: null, originPath: null, context: null });
	persistActivePlayback(null, null);
}

export function setKeepPlayingOnNavigate(enabled: boolean): void {
	setKeepPlayingOnNavigateEnabled(enabled);
	keepPlayingOnNavigate.set(enabled);
}

export function setAutoSkipCommercials(enabled: boolean): void {
	setAutoSkipCommercialsEnabled(enabled);
	autoSkipCommercials.set(enabled);
}

if (typeof window !== 'undefined') {
	restoreActivePlayback();
	window.addEventListener('pagehide', () => {
		stopCurrent();
	});
}
