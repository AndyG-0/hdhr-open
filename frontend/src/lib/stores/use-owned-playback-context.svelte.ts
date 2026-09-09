import { get } from 'svelte/store';
import { playback, updateContext, type PlaybackContext } from './playback';

/**
 * Keeps the persistent player's context fresh whenever reactive state read
 * in `buildContext` changes, but only while the current page is the one that
 * started playback (`originPath === pathname`).
 */
export function useOwnedPlaybackContext(
	pathname: string | (() => string),
	buildContext: () => PlaybackContext,
): void {
	$effect(() => {
		const context = buildContext();
		const current = get(playback);
		const targetPath = typeof pathname === 'function' ? pathname() : pathname;
		if (current.media && current.originPath === targetPath) {
			updateContext(context);
		}
	});
}
