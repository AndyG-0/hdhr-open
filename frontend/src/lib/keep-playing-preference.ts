const KEEP_PLAYING_KEY = 'hdhomerun_keep_playing_on_navigate';

export function isKeepPlayingOnNavigateEnabled(): boolean {
	if (typeof localStorage === 'undefined') return false;
	try {
		return localStorage.getItem(KEEP_PLAYING_KEY) === 'true';
	} catch {
		return false;
	}
}

export function setKeepPlayingOnNavigateEnabled(enabled: boolean): void {
	if (typeof localStorage === 'undefined') return;
	try {
		if (enabled) {
			localStorage.setItem(KEEP_PLAYING_KEY, 'true');
		} else {
			localStorage.removeItem(KEEP_PLAYING_KEY);
		}
	} catch {
		// Ignore storage access errors in restricted contexts
	}
}
