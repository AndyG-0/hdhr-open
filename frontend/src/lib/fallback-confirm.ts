const FALLBACK_CONFIRM_KEY = 'hdhomerun_suppress_fallback_confirm';

export function isFallbackConfirmSuppressed(): boolean {
	if (typeof localStorage === 'undefined') return false;
	try {
		return localStorage.getItem(FALLBACK_CONFIRM_KEY) === 'true';
	} catch {
		return false;
	}
}

export function setFallbackConfirmSuppressed(suppressed: boolean): void {
	if (typeof localStorage === 'undefined') return;
	try {
		if (suppressed) {
			localStorage.setItem(FALLBACK_CONFIRM_KEY, 'true');
		} else {
			localStorage.removeItem(FALLBACK_CONFIRM_KEY);
		}
	} catch {
		// Ignore storage access errors in restricted contexts
	}
}
