import { api } from '$lib/api';

// Keeps a watch session alive on the backend (see watch.py) by pinging it
// periodically while a stream is active - the backend expires a session
// that stops hearing from the client, so the player and the single/
// multi-view stores both need this. Factored out here since playback.ts
// (one session at a time) and multiview.ts (one session per slot) used to
// each hand-roll their own setInterval/clearInterval bookkeeping for the
// exact same keep-alive ping.
const WATCH_HEARTBEAT_INTERVAL_MS = 20_000;

export interface WatchSessionHeartbeat {
	/** (Re)starts the heartbeat for `key`, replacing any heartbeat already running under it. */
	start: (key: string, watchSessionId: string) => void;
	/** Stops the heartbeat for `key`, if one is running. */
	stop: (key: string) => void;
	/** Stops every heartbeat this instance is tracking. */
	stopAll: () => void;
}

export function createWatchSessionHeartbeat(): WatchSessionHeartbeat {
	const handles = new Map<string, ReturnType<typeof setInterval>>();

	function stop(key: string) {
		const handle = handles.get(key);
		if (handle !== undefined) {
			clearInterval(handle);
			handles.delete(key);
		}
	}

	function start(key: string, watchSessionId: string) {
		stop(key);
		const handle = setInterval(() => {
			api.heartbeatWatch(watchSessionId).catch(() => {});
		}, WATCH_HEARTBEAT_INTERVAL_MS);
		handles.set(key, handle);
	}

	function stopAll() {
		for (const handle of handles.values()) {
			clearInterval(handle);
		}
		handles.clear();
	}

	return { start, stop, stopAll };
}
