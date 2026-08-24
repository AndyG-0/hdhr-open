import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import { api } from '$lib/api';

const STORAGE_KEY = 'dashboard-theme';
const DEFAULT_THEME = 'dark';

function initialTheme(): string {
	if (!browser) return DEFAULT_THEME;
	return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_THEME;
}

// Synchronous, localStorage-backed init above avoids a flash of the wrong
// theme before any network call can resolve. Once a user is known,
// loadThemeFromServer() below overwrites it with their actual preference —
// this subscribe still handles caching that server value locally and
// applying it to the DOM, same as it always has.
export const theme = writable<string>(initialTheme());

theme.subscribe((value) => {
	if (!browser) return;
	localStorage.setItem(STORAGE_KEY, value);
	document.documentElement.setAttribute('data-theme', value);
});

export function loadThemeFromServer() {
	return api
		.getPreferences()
		.then((prefs) => theme.set(prefs.theme))
		.catch(() => {
			// keep whatever the localStorage-seeded value was
		});
}

// Persist a theme *change* explicitly from the call site (e.g. cycleTheme)
// rather than a blanket store subscribe — a subscribe would also fire (and
// PATCH) when loadThemeFromServer itself just set the value, or before a
// user is even logged in.
export function persistTheme(value: string) {
	return api.updatePreferences({ theme: value }).catch(() => {
		// best-effort — the local value (and localStorage) already changed
	});
}
