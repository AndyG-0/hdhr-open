import { writable } from 'svelte/store';
import { browser } from '$app/environment';

// Must match the `@media (max-width: 700px)` breakpoint in +page.svelte,
// where the dashboard grid drops its 2D col/row layout and stacks tiles
// full-width in DOM order.
export const NARROW_MAX_WIDTH = 700;

export type Breakpoint = 'wide' | 'narrow';

function currentBreakpoint(): Breakpoint {
	if (!browser) return 'wide';
	return window.innerWidth <= NARROW_MAX_WIDTH ? 'narrow' : 'wide';
}

export const breakpoint = writable<Breakpoint>(currentBreakpoint());

// A plain `resize` listener (rather than `matchMedia`, which jsdom doesn't
// implement) reacting to the threshold being crossed — e.g. a tablet
// rotated, or a browser window resized — not on every pixel of resize.
if (browser) {
	window.addEventListener('resize', () => breakpoint.set(currentBreakpoint()));
}
