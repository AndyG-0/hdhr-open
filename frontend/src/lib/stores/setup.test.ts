import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const { setupStatus } = vi.hoisted(() => ({ setupStatus: vi.fn() }));
vi.mock('$lib/api', () => ({
	api: { setupStatus },
	describeFetchError: (error: unknown) => (error instanceof TypeError ? 'network' : 'server'),
}));

beforeEach(() => {
	vi.resetModules();
	setupStatus.mockReset();
});

describe('setup store', () => {
	it('starts as not-needed and not loaded', async () => {
		const { needsSetup, setupStatusLoaded, setupStatusError } = await import('./setup');

		expect(get(needsSetup)).toBe(false);
		expect(get(setupStatusLoaded)).toBe(false);
		expect(get(setupStatusError)).toBeNull();
	});

	it('loadSetupStatus sets needsSetup and marks loaded on success', async () => {
		setupStatus.mockResolvedValue({ needs_setup: true });

		const { needsSetup, setupStatusLoaded, setupStatusError, loadSetupStatus } = await import('./setup');
		const result = await loadSetupStatus();

		expect(get(needsSetup)).toBe(true);
		expect(get(setupStatusLoaded)).toBe(true);
		expect(get(setupStatusError)).toBeNull();
		expect(result).toBe(true);
	});

	it('classifies a network failure and marks loaded without touching needsSetup', async () => {
		setupStatus.mockRejectedValue(new TypeError('Failed to fetch'));

		const { needsSetup, setupStatusLoaded, setupStatusError, loadSetupStatus } = await import('./setup');
		const result = await loadSetupStatus();

		expect(get(needsSetup)).toBe(false);
		expect(get(setupStatusLoaded)).toBe(true);
		expect(get(setupStatusError)).toBe('network');
		expect(result).toBeNull();
	});

	it('classifies a non-ok server response as a server error', async () => {
		setupStatus.mockRejectedValue(new Error('Request to /api/setup/status failed: 500'));

		const { setupStatusError, loadSetupStatus } = await import('./setup');
		await loadSetupStatus();

		expect(get(setupStatusError)).toBe('server');
	});
});
