import { writable } from 'svelte/store';
import { api, describeFetchError, type FetchErrorKind } from '$lib/api';

export const needsSetup = writable(false);
export const setupStatusLoaded = writable(false);
export const setupStatusError = writable<FetchErrorKind | null>(null);

export function loadSetupStatus() {
	return api
		.setupStatus()
		.then((result) => {
			needsSetup.set(result.needs_setup);
			setupStatusError.set(null);
			return result.needs_setup;
		})
		.catch((error) => {
			// Unknown either way — don't claim setup is or isn't needed when we
			// couldn't reach the backend to ask.
			setupStatusError.set(describeFetchError(error));
			return null;
		})
		.finally(() => setupStatusLoaded.set(true));
}
