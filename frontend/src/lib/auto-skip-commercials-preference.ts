const AUTO_SKIP_COMMERCIALS_KEY = 'hdhomerun_auto_skip_commercials';

export function isAutoSkipCommercialsEnabled(): boolean {
	if (typeof localStorage === 'undefined') return false;
	try {
		return localStorage.getItem(AUTO_SKIP_COMMERCIALS_KEY) === 'true';
	} catch {
		return false;
	}
}

export function setAutoSkipCommercialsEnabled(enabled: boolean): void {
	if (typeof localStorage === 'undefined') return;
	try {
		if (enabled) {
			localStorage.setItem(AUTO_SKIP_COMMERCIALS_KEY, 'true');
		} else {
			localStorage.removeItem(AUTO_SKIP_COMMERCIALS_KEY);
		}
	} catch {
		// Ignore storage access errors in restricted contexts
	}
}
