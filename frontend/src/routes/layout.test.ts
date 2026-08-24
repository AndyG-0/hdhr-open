import { render, screen } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';

const { goto, registerDevice, currentUser, setupStatus, getPreferences, pageState } = vi.hoisted(
	() => ({
		goto: vi.fn(),
		registerDevice: vi.fn(),
		currentUser: vi.fn(),
		setupStatus: vi.fn(),
		getPreferences: vi.fn(),
		pageState: { url: new URL('http://localhost/') },
	}),
);
vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$app/state', () => ({ page: pageState }));
vi.mock('$lib/api', () => ({
	api: {
		registerDevice,
		renameDevice: vi.fn(),
		currentUser,
		logoutUser: vi.fn(),
		setupStatus,
		getPreferences,
	},
	describeFetchError: (error: unknown) => (error instanceof TypeError ? 'network' : 'server'),
}));

import Layout from './+layout.svelte';
import { user, userLoaded } from '$lib/stores/user';
import { needsSetup, setupStatusLoaded, setupStatusError } from '$lib/stores/setup';
import { device } from '$lib/stores/device';

function emptyChildren() {
	return createRawSnippet(() => ({ render: () => '<div data-testid="app-content"></div>' }));
}

async function flush() {
	await new Promise((resolve) => setTimeout(resolve, 0));
	await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('+layout.svelte', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		pageState.url = new URL('http://localhost/');
		user.set(null);
		userLoaded.set(false);
		needsSetup.set(false);
		setupStatusLoaded.set(false);
		setupStatusError.set(null);
		device.set(null);
		registerDevice.mockResolvedValue({ id: 'd1', name: 'New Device', is_new: false });
		getPreferences.mockReturnValue(new Promise(() => {}));
	});

	it('redirects to /setup on a fresh install with no admin yet', async () => {
		setupStatus.mockResolvedValue({ needs_setup: true });
		currentUser.mockRejectedValue(new Error('401'));

		render(Layout, { props: { children: emptyChildren() } });
		await flush();

		expect(goto).toHaveBeenCalledWith('/setup');
	});

	it('redirects away from /setup once setup has already been completed', async () => {
		pageState.url = new URL('http://localhost/setup');
		setupStatus.mockResolvedValue({ needs_setup: false });
		currentUser.mockRejectedValue(new Error('401'));

		render(Layout, { props: { children: emptyChildren() } });
		await flush();

		expect(goto).toHaveBeenCalledWith('/login');
	});

	it('redirects to /login when setup is complete and there is no session', async () => {
		setupStatus.mockResolvedValue({ needs_setup: false });
		currentUser.mockRejectedValue(new Error('401'));

		render(Layout, { props: { children: emptyChildren() } });
		await flush();

		expect(goto).toHaveBeenCalledWith('/login');
	});

	it('does not redirect once a session is present', async () => {
		setupStatus.mockResolvedValue({ needs_setup: false });
		currentUser.mockResolvedValue({ id: 'u1', name: 'Alice', avatar: null, role: 'admin' });

		render(Layout, { props: { children: emptyChildren() } });
		await flush();

		expect(goto).not.toHaveBeenCalled();
		expect(get(user)).toEqual({ id: 'u1', name: 'Alice', avatar: null, role: 'admin' });
	});

	it('shows an unreachable-backend message and does not redirect when the backend is unreachable', async () => {
		setupStatus.mockRejectedValue(new TypeError('Failed to fetch'));
		currentUser.mockRejectedValue(new TypeError('Failed to fetch'));

		render(Layout, { props: { children: emptyChildren() } });
		await flush();

		expect(screen.getByText('Could not reach the HDHR Open backend')).toBeInTheDocument();
		expect(screen.queryByTestId('app-content')).not.toBeInTheDocument();
		expect(goto).not.toHaveBeenCalled();
	});
});
