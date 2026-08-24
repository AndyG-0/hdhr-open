import { describe, expect, it, vi } from 'vitest';

const { onMount } = vi.hoisted(() => ({
	onMount: vi.fn((fn: () => void | (() => void)) => fn()),
}));
vi.mock('svelte', () => ({ onMount }));

import { pollWidget } from './polling';

describe('pollWidget', () => {
	it('calls refresh immediately, then again on each interval tick', () => {
		vi.useFakeTimers();
		try {
			const refresh = vi.fn();
			pollWidget(refresh, 1000);
			expect(refresh).toHaveBeenCalledTimes(1);

			vi.advanceTimersByTime(1000);
			expect(refresh).toHaveBeenCalledTimes(2);

			vi.advanceTimersByTime(2000);
			expect(refresh).toHaveBeenCalledTimes(4);
		} finally {
			vi.useRealTimers();
		}
	});

	it('stops polling once the onMount cleanup runs', () => {
		vi.useFakeTimers();
		try {
			let cleanup: (() => void) | undefined;
			onMount.mockImplementationOnce((fn: () => void | (() => void)) => {
				cleanup = fn() as (() => void) | undefined;
			});

			const refresh = vi.fn();
			pollWidget(refresh, 1000);
			cleanup?.();

			vi.advanceTimersByTime(5000);
			expect(refresh).toHaveBeenCalledTimes(1); // only the initial call
		} finally {
			vi.useRealTimers();
		}
	});
});
