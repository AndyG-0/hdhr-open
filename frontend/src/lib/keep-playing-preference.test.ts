import { describe, expect, it, beforeEach } from 'vitest';
import { isKeepPlayingOnNavigateEnabled, setKeepPlayingOnNavigateEnabled } from './keep-playing-preference';

describe('keep-playing-preference', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	it('defaults to disabled', () => {
		expect(isKeepPlayingOnNavigateEnabled()).toBe(false);
	});

	it('persists enabling and disabling across reads', () => {
		setKeepPlayingOnNavigateEnabled(true);
		expect(isKeepPlayingOnNavigateEnabled()).toBe(true);

		setKeepPlayingOnNavigateEnabled(false);
		expect(isKeepPlayingOnNavigateEnabled()).toBe(false);
	});

	it('removes the stored key entirely when disabled', () => {
		setKeepPlayingOnNavigateEnabled(true);
		setKeepPlayingOnNavigateEnabled(false);
		expect(localStorage.getItem('hdhomerun_keep_playing_on_navigate')).toBeNull();
	});
});
