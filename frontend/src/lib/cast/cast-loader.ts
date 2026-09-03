// Thin wrapper around the Google Cast Sender SDK, lazily loaded (Chrome
// desktop/Android only - every other browser never calls
// `__onGCastApiAvailable`, so callers must not await loadCastApi()
// unconditionally on mount; watchCastState below is the one safe thing to
// call eagerly, since it just never fires its callback elsewhere).
//
// Deliberately declares only the narrow slice of the SDK's surface this
// module actually touches, rather than depending on @types/chromecast-caf-sender
// (no other Google-supplied ambient-type package exists in this codebase,
// and pulling one in just for this wrapper isn't worth it) - mirrors
// caption-controller.ts/mpegts-player.ts's closures-over-callbacks module
// shape rather than a class, matching this codebase's convention for
// player-adjacent modules.

const CAST_SENDER_SRC = 'https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1';

export type CastState = 'no_devices_available' | 'not_connected' | 'connecting' | 'connected';

interface CastSession {
	loadMedia(request: CastLoadRequest): Promise<void>;
}

interface CastContext {
	setOptions(options: { receiverApplicationId: string; autoJoinPolicy: string }): void;
	getCurrentSession(): CastSession | null;
	requestSession(): Promise<void>;
	endCurrentSession(stopCasting: boolean): void;
	getCastState(): CastState;
	addEventListener(type: string, listener: (event: { castState: CastState }) => void): void;
	removeEventListener(type: string, listener: (event: { castState: CastState }) => void): void;
}

export interface RemotePlayer {
	isPaused: boolean;
	isMediaLoaded: boolean;
	currentTime: number;
	duration: number;
}

export interface RemotePlayerController {
	addEventListener(type: string, listener: () => void): void;
	removeEventListener(type: string, listener: () => void): void;
	playOrPause(): void;
	seek(): void;
	stop(): void;
}

interface CastFramework {
	CastContext: { getInstance(): CastContext };
	CastContextEventType: { CAST_STATE_CHANGED: string };
	RemotePlayer: new () => RemotePlayer;
	RemotePlayerController: new (player: RemotePlayer) => RemotePlayerController;
	RemotePlayerEventType: {
		IS_PAUSED_CHANGED: string;
		IS_MEDIA_LOADED_CHANGED: string;
	};
}

interface CastApi {
	framework: CastFramework;
}

interface CastMediaMetadata {
	title?: string;
	subtitle?: string;
	images?: unknown[];
}

interface CastMediaInfo {
	metadata?: CastMediaMetadata;
}

interface CastLoadRequest {
	media: CastMediaInfo;
}

interface ChromeCastApi {
	media: {
		DEFAULT_MEDIA_RECEIVER_APP_ID: string;
		MediaInfo: new (contentUrl: string, contentType: string) => CastMediaInfo;
		GenericMediaMetadata: new () => CastMediaMetadata;
		LoadRequest: new (mediaInfo: CastMediaInfo) => CastLoadRequest;
	};
	Image: new (url: string) => unknown;
	AutoJoinPolicy: { ORIGIN_SCOPED: string };
}

declare global {
	interface Window {
		cast?: CastApi;
		chrome?: { cast?: ChromeCastApi };
		__onGCastApiAvailable?: (isAvailable: boolean) => void;
	}
}

let apiPromise: Promise<CastApi> | null = null;

// The Cast SDK's CastContext is page/tab-scoped (window.cast), so a cast
// session naturally survives a SvelteKit client-side route navigation - only
// the CastButton *component* that started it gets unmounted. Tracking the
// backend's for_cast HLS session id here too (rather than as component-local
// state) means whichever CastButton instance is mounted later, on whatever
// page the user navigated to, can still discover and correctly stop the
// right backend session - on an explicit stop-click there, or on a
// receiver-side disconnect noticed via watchCastState.
let activeBackendSessionId: string | null = null;

export function getActiveCastSessionId(): string | null {
	return activeBackendSessionId;
}

export function setActiveCastSessionId(id: string | null): void {
	activeBackendSessionId = id;
}

export function loadCastApi(): Promise<CastApi> {
	// Checked fresh on every call, ahead of the cache below - the SDK script
	// only ever needs injecting once, but pinning *that* promise forever
	// would mean a single failed/never-called load (or, in a test, a stub
	// swapped out between cases) permanently wins over window.cast actually
	// being present right now.
	if (typeof window !== 'undefined' && window.cast?.framework && window.chrome?.cast) {
		return Promise.resolve(window.cast);
	}
	if (apiPromise) return apiPromise;
	apiPromise = new Promise((resolve, reject) => {
		if (typeof window === 'undefined') {
			reject(new Error('Google Cast is only available in a browser'));
			return;
		}
		window.__onGCastApiAvailable = (isAvailable: boolean) => {
			if (!isAvailable || !window.cast?.framework || !window.chrome?.cast) {
				reject(new Error('Google Cast API unavailable'));
				return;
			}
			window.cast.framework.CastContext.getInstance().setOptions({
				receiverApplicationId: window.chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
				autoJoinPolicy: window.chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
			});
			resolve(window.cast);
		};
		const script = document.createElement('script');
		script.src = CAST_SENDER_SRC;
		script.onerror = () => reject(new Error('Failed to load the Google Cast sender SDK'));
		document.head.appendChild(script);
	});
	return apiPromise;
}

/** Subscribes to Cast availability/connection-state changes, so a Cast
 * button knows whether to render at all (no devices on the network => stay
 * hidden entirely, the same "only show when a route exists" behavior as the
 * AirPlay button's webkitplaybacktargetavailabilitychanged listener).
 * Returns an unsubscribe function; safe to call unconditionally even in a
 * browser that never loads the Cast API - onChange just never fires. */
export function watchCastState(onChange: (state: CastState) => void): () => void {
	let unsubscribe: (() => void) | null = null;
	let cancelled = false;
	loadCastApi()
		.then((castApi) => {
			if (cancelled) return;
			const context = castApi.framework.CastContext.getInstance();
			const listener = (event: { castState: CastState }) => onChange(event.castState);
			context.addEventListener(castApi.framework.CastContextEventType.CAST_STATE_CHANGED, listener);
			onChange(context.getCastState());
			unsubscribe = () =>
				context.removeEventListener(castApi.framework.CastContextEventType.CAST_STATE_CHANGED, listener);
		})
		.catch(() => {
			// Cast unsupported in this browser - never calls onChange, button stays hidden.
		});
	return () => {
		cancelled = true;
		unsubscribe?.();
	};
}

export interface CastMediaRequest {
	contentUrl: string;
	contentType: string;
	title: string;
	subtitle?: string;
	imageUrl?: string;
}

/** Opens (or joins an already-open) a Cast session - MUST be called and
 * awaited before anything else async happens in a click handler. Chrome only
 * honors `CastContext.requestSession()`'s native device-picker popup while
 * the click's transient user-activation is still live (a few seconds); any
 * slow await placed ahead of this call (e.g. minting the backend's HLS
 * session first, which can take several seconds while ffmpeg spins up) burns
 * through that window, and requestSession() then just never resolves - no
 * picker ever appears and the caller hangs forever. Do the slow work (see
 * `loadCastMedia` below) only after this resolves. */
export async function requestCastSession(): Promise<CastSession> {
	const castApi = await loadCastApi();
	const context = castApi.framework.CastContext.getInstance();
	let session = context.getCurrentSession();
	if (!session) {
		await context.requestSession();
		session = context.getCurrentSession();
	}
	if (!session) throw new Error('No active Cast session');
	return session;
}

/** Loads `request` onto an already-open `session` (see `requestCastSession`). */
export async function loadCastMedia(session: CastSession, request: CastMediaRequest): Promise<void> {
	const chromeCast = window.chrome!.cast!;
	const mediaInfo = new chromeCast.media.MediaInfo(request.contentUrl, request.contentType);
	mediaInfo.metadata = new chromeCast.media.GenericMediaMetadata();
	mediaInfo.metadata.title = request.title;
	if (request.subtitle) mediaInfo.metadata.subtitle = request.subtitle;
	if (request.imageUrl) mediaInfo.metadata.images = [new chromeCast.Image(request.imageUrl)];

	await session.loadMedia(new chromeCast.media.LoadRequest(mediaInfo));
}

export function endCastSession(): void {
	window.cast?.framework.CastContext.getInstance().endCurrentSession(true);
}

/** A RemotePlayer/RemotePlayerController pair mirrors play/pause/seek state
 * for whatever's currently loaded on the receiver - only meaningful once a
 * session is active, but constructing them is cheap/safe beforehand (the
 * SDK just reports isMediaLoaded=false until then). */
export function createRemotePlayer(castApi: CastApi): {
	remotePlayer: RemotePlayer;
	controller: RemotePlayerController;
} {
	const remotePlayer = new castApi.framework.RemotePlayer();
	const controller = new castApi.framework.RemotePlayerController(remotePlayer);
	return { remotePlayer, controller };
}
