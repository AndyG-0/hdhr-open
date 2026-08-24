import { writable } from 'svelte/store';
import { api, type CurrentUser } from '$lib/api';

// null means "not logged in" — distinct from undefined/not-yet-checked,
// which is what `loaded` tracks below.
export const user = writable<CurrentUser | null>(null);
export const userLoaded = writable(false);

export function loadCurrentUser() {
	return api
		.currentUser()
		.then((result) => {
			user.set(result);
			return result;
		})
		.catch(() => {
			user.set(null);
			return null;
		})
		.finally(() => userLoaded.set(true));
}

export function logout() {
	return api.logoutUser().finally(() => user.set(null));
}
