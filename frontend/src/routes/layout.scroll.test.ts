import { render } from '@testing-library/svelte';
import { createRawSnippet } from 'svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { goto, currentUser, setupStatus, getPreferences, pageState } = vi.hoisted(() => ({
	goto: vi.fn(),
	currentUser: vi.fn(),
	setupStatus: vi.fn(),
	getPreferences: vi.fn(),
	pageState: { url: new URL('http://localhost/') },
}));
vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$app/state', () => ({ page: pageState }));
vi.mock('$lib/api', () => ({
	api: {
		currentUser,
		logoutUser: vi.fn(),
		setupStatus,
		getPreferences,
		getNetworkIntegration: vi.fn().mockResolvedValue({ settings: {} }),
		getHDHomeRunChannels: vi.fn().mockResolvedValue({ channels: [] }),
		getTunerInfo: vi.fn().mockResolvedValue(null),
		getTunerStatus: vi.fn().mockResolvedValue([]),
	},
	describeFetchError: (error: unknown) => (error instanceof TypeError ? 'network' : 'server'),
}));

vi.mock('$lib/mpegts-player', () => ({
	createMpegtsPlayer: () => ({
		createPlayerAt: vi.fn(),
		teardownPlayer: vi.fn(),
		fetchServerDetail: vi.fn(),
	}),
}));

import Layout from './+layout.svelte';
import MultiViewPlayer from '$lib/components/player/multiview/MultiViewPlayer.svelte';
import PlayerPage from './player/+page.svelte';
import { user, userLoaded } from '$lib/stores/user';
import { needsSetup, setupStatusLoaded, setupStatusError } from '$lib/stores/setup';
import { closeAll } from '$lib/stores/multiview';

function emptyChildren() {
	return createRawSnippet(() => ({ render: () => '<div data-testid="app-content"></div>' }));
}

async function flush() {
	await new Promise((resolve) => setTimeout(resolve, 0));
	await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('Scroll behavior and overflow locking', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		document.body.style.overflow = '';
		pageState.url = new URL('http://localhost/');
		user.set(null);
		userLoaded.set(false);
		needsSetup.set(false);
		setupStatusLoaded.set(false);
		setupStatusError.set(null);
		getPreferences.mockReturnValue(new Promise(() => {}));
		closeAll();
	});

	it('does not apply overflow: hidden to body when rendering +layout.svelte with no active players', async () => {
		setupStatus.mockResolvedValue({ needs_setup: false });
		currentUser.mockResolvedValue({ id: 'u1', name: 'Alice', avatar: null, role: 'admin' });

		render(Layout, { props: { children: emptyChildren() } });
		await flush();

		expect(document.body.style.overflow).not.toBe('hidden');
	});

	it('MultiViewPlayer locks body overflow while mounted and restores previous overflow on unmount', async () => {
		document.body.style.overflow = 'auto';

		const { unmount } = render(MultiViewPlayer, { props: {} });
		await flush();

		expect(document.body.style.overflow).toBe('hidden');

		unmount();
		await flush();

		expect(document.body.style.overflow).toBe('auto');
	});

	it('player/+page.svelte locks body overflow while mounted and restores previous overflow on unmount', async () => {
		document.body.style.overflow = '';

		const { unmount } = render(PlayerPage);
		await flush();

		expect(document.body.style.overflow).toBe('hidden');

		unmount();
		await flush();

		expect(document.body.style.overflow).toBe('');
	});
});
