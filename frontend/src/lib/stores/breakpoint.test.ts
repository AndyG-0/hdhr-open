import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

function setInnerWidth(width: number) {
	Object.defineProperty(window, 'innerWidth', { configurable: true, value: width });
}

const originalInnerWidth = window.innerWidth;

beforeEach(() => {
	vi.resetModules();
	setInnerWidth(originalInnerWidth);
});

afterEach(() => {
	setInnerWidth(originalInnerWidth);
});

describe('breakpoint store', () => {
	it('starts wide above the 700px threshold', async () => {
		setInnerWidth(1024);

		const { breakpoint } = await import('./breakpoint');

		expect(get(breakpoint)).toBe('wide');
	});

	it('starts narrow at or below the 700px threshold', async () => {
		setInnerWidth(700);

		const { breakpoint } = await import('./breakpoint');

		expect(get(breakpoint)).toBe('narrow');
	});

	it('updates when the window is resized across the threshold', async () => {
		setInnerWidth(1024);

		const { breakpoint } = await import('./breakpoint');
		expect(get(breakpoint)).toBe('wide');

		setInnerWidth(500);
		window.dispatchEvent(new Event('resize'));

		expect(get(breakpoint)).toBe('narrow');
	});
});
