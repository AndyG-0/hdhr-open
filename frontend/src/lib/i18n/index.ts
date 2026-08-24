import { register, init, locale, waitLocale } from 'svelte-i18n';
import { browser } from '$app/environment';
import { api } from '$lib/api';

const STORAGE_KEY = 'dashboard-locale';
const DEFAULT_LOCALE = 'en';

register('en', () => import('./locales/en.json'));
register('es', () => import('./locales/es.json'));
register('fr', () => import('./locales/fr.json'));
register('de', () => import('./locales/de.json'));

function initialLocale(): string {
	if (!browser) return DEFAULT_LOCALE;
	return localStorage.getItem(STORAGE_KEY) ?? DEFAULT_LOCALE;
}

init({
	fallbackLocale: DEFAULT_LOCALE,
	initialLocale: initialLocale(),
});

locale.subscribe((value) => {
	if (!browser || !value) return;
	localStorage.setItem(STORAGE_KEY, value);
});

export function loadLocaleFromServer() {
	return api
		.getPreferences()
		.then((prefs) => locale.set(prefs.locale))
		.catch(() => {
			// keep whatever the localStorage-seeded value was
		});
}

export function persistLocale(value: string) {
	return api.updatePreferences({ locale: value }).catch(() => {
		// best-effort — the local value (and localStorage) already changed
	});
}

export { locale, waitLocale };
