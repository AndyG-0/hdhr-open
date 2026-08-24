import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { scrollFade } from './scrollFade';

class FakeResizeObserver {
	observe = vi.fn();
	disconnect = vi.fn();
}

function makeScrollable(scrollHeight: number, clientHeight: number, scrollTop = 0): HTMLElement {
	const wrap = document.createElement('div');
	const node = document.createElement('div');
	wrap.appendChild(node);
	Object.defineProperty(node, 'scrollHeight', { value: scrollHeight, configurable: true });
	Object.defineProperty(node, 'clientHeight', { value: clientHeight, configurable: true });
	Object.defineProperty(node, 'scrollTop', { value: scrollTop, configurable: true, writable: true });
	return node;
}

describe('scrollFade', () => {
	beforeEach(() => {
		vi.stubGlobal('ResizeObserver', FakeResizeObserver);
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('marks neither edge when content fits without scrolling', () => {
		const node = makeScrollable(100, 100);
		scrollFade(node);

		expect(node.parentElement?.classList.contains('fade-top')).toBe(false);
		expect(node.parentElement?.classList.contains('fade-bottom')).toBe(false);
	});

	it('marks fade-bottom when scrolled to the top with more content below', () => {
		const node = makeScrollable(300, 100, 0);
		scrollFade(node);

		expect(node.parentElement?.classList.contains('fade-top')).toBe(false);
		expect(node.parentElement?.classList.contains('fade-bottom')).toBe(true);
	});

	it('marks fade-top once scrolled away from the top', () => {
		const node = makeScrollable(300, 100, 50);
		scrollFade(node);

		expect(node.parentElement?.classList.contains('fade-top')).toBe(true);
		expect(node.parentElement?.classList.contains('fade-bottom')).toBe(true);
	});

	it('clears fade-bottom once scrolled to the end', () => {
		const node = makeScrollable(300, 100, 200);
		scrollFade(node);

		expect(node.parentElement?.classList.contains('fade-top')).toBe(true);
		expect(node.parentElement?.classList.contains('fade-bottom')).toBe(false);
	});

	it('recomputes on scroll events', () => {
		const node = makeScrollable(300, 100, 0);
		scrollFade(node);
		expect(node.parentElement?.classList.contains('fade-top')).toBe(false);

		Object.defineProperty(node, 'scrollTop', { value: 200, configurable: true });
		node.dispatchEvent(new Event('scroll'));

		expect(node.parentElement?.classList.contains('fade-top')).toBe(true);
		expect(node.parentElement?.classList.contains('fade-bottom')).toBe(false);
	});

	it('stops updating on scroll after destroy', () => {
		const node = makeScrollable(300, 100, 0);
		const action = scrollFade(node);
		action?.destroy();

		Object.defineProperty(node, 'scrollTop', { value: 200, configurable: true });
		node.dispatchEvent(new Event('scroll'));

		expect(node.parentElement?.classList.contains('fade-top')).toBe(false);
	});

	it('exposes an update function that can be called again (e.g. on dependency change)', () => {
		const node = makeScrollable(300, 100, 0);
		const action = scrollFade(node);

		Object.defineProperty(node, 'scrollHeight', { value: 100, configurable: true });
		action?.update();

		expect(node.parentElement?.classList.contains('fade-bottom')).toBe(false);
	});
});
