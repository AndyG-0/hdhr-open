import { writable, get } from 'svelte/store';
import { browser } from '$app/environment';
import { api } from '$lib/api';

const STORAGE_KEY = 'dashboard-theme';
const DEFAULT_THEME = 'system';

const media = browser ? window.matchMedia('(prefers-color-scheme: dark)') : null;

// "system" is a preference like any other theme id, but it has no CSS file
// of its own — resolve() maps it to whichever concrete theme should actually
// be painted, based on the OS-level scheme.
function resolve(pref: string): string {
	return pref === 'system' ? (media?.matches ? 'dark' : 'light') : pref;
}

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
	document.documentElement.setAttribute('data-theme', resolve(value));
});

// Live-update the DOM if the OS-level scheme changes while "system" is selected.
media?.addEventListener('change', () => {
	if (get(theme) === 'system') {
		document.documentElement.setAttribute('data-theme', resolve('system'));
	}
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
