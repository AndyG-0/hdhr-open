import '@testing-library/jest-dom/vitest';
import { register, init, waitLocale } from 'svelte-i18n';

// All four locales are registered (mirroring the real app's bootstrap) so
// tests that explicitly switch locale can assert on translated text.
// Waiting for 'en' here means every test's `$_()` calls resolve real
// English strings synchronously by default, so existing assertions against
// literal English text keep passing unmodified.
register('en', () => import('./lib/i18n/locales/en.json'));
register('es', () => import('./lib/i18n/locales/es.json'));
register('fr', () => import('./lib/i18n/locales/fr.json'));
register('de', () => import('./lib/i18n/locales/de.json'));
init({ fallbackLocale: 'en', initialLocale: 'en' });
await waitLocale();

// Node 26+ defines its own experimental global `localStorage` getter (gated
// behind --localstorage-file) that returns undefined. Since vitest's jsdom
// environment aliases `window` to `globalThis`, this shadows jsdom's real
// Storage instance too — `window.localStorage` hits the same broken getter.
// Replace it outright with a minimal in-memory Storage polyfill.
{
	const store = new Map<string, string>();
	const localStoragePolyfill: Storage = {
		getItem: (key) => (store.has(key) ? store.get(key)! : null),
		setItem: (key, value) => {
			store.set(key, String(value));
		},
		removeItem: (key) => {
			store.delete(key);
		},
		clear: () => {
			store.clear();
		},
		key: (index) => Array.from(store.keys())[index] ?? null,
		get length() {
			return store.size;
		},
	};
	Object.defineProperty(globalThis, 'localStorage', {
		value: localStoragePolyfill,
		configurable: true,
		writable: true,
	});
}

// jsdom doesn't implement ResizeObserver; components only use it to detect
// content-size changes (e.g. scrollFade), which isn't relevant in tests.
if (typeof globalThis.ResizeObserver === 'undefined') {
	globalThis.ResizeObserver = class {
		observe() {}
		unobserve() {}
		disconnect() {}
	};
}

// jsdom doesn't implement IntersectionObserver; used only to trigger
// infinite-scroll pagination on the recordings page, which isn't exercised
// by these tests.
if (typeof globalThis.IntersectionObserver === 'undefined') {
	globalThis.IntersectionObserver = class {
		observe() {}
		unobserve() {}
		disconnect() {}
	} as unknown as typeof IntersectionObserver;
}

// jsdom doesn't implement matchMedia; the theme store uses it to resolve
// "system" mode. Default to "light preferred" (matches: false) — tests that
// care about the resolved OS scheme can override window.matchMedia directly.
if (typeof window.matchMedia !== 'function') {
	window.matchMedia = (query: string) =>
		({
			matches: false,
			media: query,
			onchange: null,
			addEventListener() {},
			removeEventListener() {},
			addListener() {},
			removeListener() {},
			dispatchEvent() {
				return false;
			},
		}) as MediaQueryList;
}

// jsdom doesn't implement the Web Animations API, which Svelte's transition
// directives (e.g. `transition:fade`) use internally via `element.animate()`.
// Without this, any test that swaps a `{#key}`-ed, transitioning element
// throws "element.animate is not a function" as an unhandled exception.
// Resolving `onfinish` on a microtask lets Svelte's two-phase transition
// (a zero-duration "delay" animation, then the real one) advance through
// both phases on its own.
if (typeof Element.prototype.animate !== 'function') {
	Element.prototype.animate = function () {
		const animation = {
			playState: 'running',
			currentTime: 0,
			effect: null,
			onfinish: null as (() => void) | null,
			cancel() {
				this.playState = 'idle';
			},
		};
		queueMicrotask(() => {
			animation.playState = 'finished';
			animation.onfinish?.();
		});
		return animation as unknown as Animation;
	};
}
