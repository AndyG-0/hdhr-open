import { writable } from 'svelte/store';
import { api, type DeviceInfo } from '$lib/api';

export const device = writable<DeviceInfo | null>(null);

// Idempotent — a browser with a valid device cookie gets the same device
// back every time, so this is safe to call on every app load. Returns the
// full register result (including `is_new`) so the caller can decide
// whether to prompt for a device name.
export function ensureDevice() {
	return api.registerDevice().then((result) => {
		device.set(result);
		return result;
	});
}

export function renameDevice(name: string) {
	return api.renameDevice(name).then(device.set);
}
