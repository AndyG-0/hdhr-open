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

const WATCH_HEARTBEAT_INTERVAL_MS = 20_000;

export interface PlaybackMedia {
	title: string;
	url: string;
	playUrl?: string;
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
		channelNumber?: string,
		start?: number | null,
		options?: RecordingRuleOptions,
	) => Promise<void> | void;
	onRecordSeries?: (
		seriesId: string,
		channelNumber?: string,
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

export const keepPlayingOnNavigate = writable<boolean>(isKeepPlayingOnNavigateEnabled());

let heartbeatHandle: ReturnType<typeof setInterval> | undefined;

function stopHeartbeat() {
	if (heartbeatHandle !== undefined) {
		clearInterval(heartbeatHandle);
		heartbeatHandle = undefined;
	}
}

function startHeartbeat(sessionId: string) {
	stopHeartbeat();
	heartbeatHandle = setInterval(() => {
		api.heartbeatWatch(sessionId);
	}, WATCH_HEARTBEAT_INTERVAL_MS);
}

function stopCurrent() {
	const current = get(playback);
	stopHeartbeat();
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
	if (media.isWatchSession && media.watchSessionId) {
		startHeartbeat(media.watchSessionId);
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
}

export function setKeepPlayingOnNavigate(enabled: boolean): void {
	setKeepPlayingOnNavigateEnabled(enabled);
	keepPlayingOnNavigate.set(enabled);
}

if (typeof window !== 'undefined') {
	window.addEventListener('pagehide', () => {
		stopCurrent();
	});
}
