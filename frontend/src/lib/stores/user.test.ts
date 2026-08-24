import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const { currentUser, logoutUser } = vi.hoisted(() => ({
	currentUser: vi.fn(),
	logoutUser: vi.fn(),
}));
vi.mock('$lib/api', () => ({ api: { currentUser, logoutUser } }));

beforeEach(() => {
	vi.resetModules();
	currentUser.mockReset();
	logoutUser.mockReset();
});

describe('user store', () => {
	it('starts as null and not loaded', async () => {
		const { user, userLoaded } = await import('./user');

		expect(get(user)).toBeNull();
		expect(get(userLoaded)).toBe(false);
	});

	it('loadCurrentUser sets the user and marks loaded on success', async () => {
		const me = { id: 'u1', name: 'Alice', avatar: null, role: 'member' as const };
		currentUser.mockResolvedValue(me);

		const { user, userLoaded, loadCurrentUser } = await import('./user');
		const result = await loadCurrentUser();

		expect(get(user)).toEqual(me);
		expect(get(userLoaded)).toBe(true);
		expect(result).toEqual(me);
	});

	it('loadCurrentUser sets the user to null and still marks loaded on failure', async () => {
		currentUser.mockRejectedValue(new Error('not logged in'));

		const { user, userLoaded, loadCurrentUser } = await import('./user');
		const result = await loadCurrentUser();

		expect(get(user)).toBeNull();
		expect(get(userLoaded)).toBe(true);
		expect(result).toBeNull();
	});

	it('logout clears the user after the request succeeds', async () => {
		logoutUser.mockResolvedValue({ status: 'ok' });

		const { user, logout } = await import('./user');
		user.set({ id: 'u1', name: 'Alice', avatar: null, role: 'member' });
		await logout();

		expect(get(user)).toBeNull();
	});

	it('logout clears the user even when the request fails', async () => {
		logoutUser.mockRejectedValue(new Error('network error'));

		const { user, logout } = await import('./user');
		user.set({ id: 'u1', name: 'Alice', avatar: null, role: 'member' });

		// The store is cleared via `.finally()` regardless of outcome, but
		// the rejection itself still propagates to the caller.
		await expect(logout()).rejects.toThrow('network error');

		expect(get(user)).toBeNull();
	});
});
