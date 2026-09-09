import { flushSync } from 'svelte';
import { describe, expect, it } from 'vitest';
import { loadOnceWhen } from './load-once.svelte';

describe('loadOnceWhen', () => {
	it('does not call load while the condition is false', () => {
		const ready = false;
		let calls = 0;

		const cleanup = $effect.root(() => {
			loadOnceWhen(
				() => ready,
				() => calls++,
			);
		});
		flushSync();

		expect(calls).toBe(0);
		cleanup();
	});

	it('calls load once the condition becomes true, and never again', () => {
		let ready = $state(false);
		let calls = 0;

		const cleanup = $effect.root(() => {
			loadOnceWhen(
				() => ready,
				() => calls++,
			);
		});
		flushSync();

		ready = true;
		flushSync();
		expect(calls).toBe(1);

		ready = false;
		flushSync();
		ready = true;
		flushSync();
		expect(calls).toBe(1);

		cleanup();
	});

	it('calls load immediately if the condition is already true on setup', () => {
		let calls = 0;

		const cleanup = $effect.root(() => {
			loadOnceWhen(
				() => true,
				() => calls++,
			);
		});
		flushSync();

		expect(calls).toBe(1);
		cleanup();
	});
});
