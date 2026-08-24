import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const { getPreferences, updatePreferences } = vi.hoisted(() => ({
	getPreferences: vi.fn(),
	updatePreferences: vi.fn(),
}));
vi.mock('$lib/api', () => ({ api: { getPreferences, updatePreferences } }));

beforeEach(() => {
	vi.resetModules();
	localStorage.clear();
	document.documentElement.removeAttribute('data-theme');
	getPreferences.mockReset();
	updatePreferences.mockReset();
});

describe('theme store (browser)', () => {
	beforeEach(() => {
		vi.doMock('$app/environment', () => ({ browser: true }));
	});

	it('defaults to dark when nothing is stored', async () => {
		const { theme } = await import('./theme');

		expect(get(theme)).toBe('dark');
		expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
	});

	it('reads a previously stored theme on init', async () => {
		localStorage.setItem('dashboard-theme', 'light');

		const { theme } = await import('./theme');

		expect(get(theme)).toBe('light');
	});

	it('persists updates to localStorage and the document element', async () => {
		const { theme } = await import('./theme');

		theme.set('light');

		expect(localStorage.getItem('dashboard-theme')).toBe('light');
		expect(document.documentElement.getAttribute('data-theme')).toBe('light');
	});

	it('loadThemeFromServer overwrites the local value with the user preference', async () => {
		localStorage.setItem('dashboard-theme', 'dark');
		getPreferences.mockResolvedValue({ theme: 'sepia' });

		const { theme, loadThemeFromServer } = await import('./theme');
		await loadThemeFromServer();

		expect(get(theme)).toBe('sepia');
	});

	it('loadThemeFromServer keeps the local value when the request fails', async () => {
		localStorage.setItem('dashboard-theme', 'contrast');
		getPreferences.mockRejectedValue(new Error('network error'));

		const { theme, loadThemeFromServer } = await import('./theme');
		await loadThemeFromServer();

		expect(get(theme)).toBe('contrast');
	});

	it('persistTheme sends the new value to the server', async () => {
		updatePreferences.mockResolvedValue({ theme: 'light' });

		const { persistTheme } = await import('./theme');
		await persistTheme('light');

		expect(updatePreferences).toHaveBeenCalledWith({ theme: 'light' });
	});

	it('persistTheme does not throw when the request fails', async () => {
		updatePreferences.mockRejectedValue(new Error('network error'));

		const { persistTheme } = await import('./theme');

		await expect(persistTheme('light')).resolves.toBeUndefined();
	});
});

describe('theme store (server)', () => {
	beforeEach(() => {
		vi.doMock('$app/environment', () => ({ browser: false }));
	});

	it('defaults to dark and never touches localStorage', async () => {
		const { theme } = await import('./theme');

		expect(get(theme)).toBe('dark');
		expect(localStorage.getItem('dashboard-theme')).toBeNull();
	});
});
