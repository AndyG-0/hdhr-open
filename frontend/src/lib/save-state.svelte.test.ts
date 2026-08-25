import { flushSync } from 'svelte';
import { describe, expect, it } from 'vitest';
import { SaveState } from './save-state.svelte';

describe('SaveState', () => {
	it('sets saving during the call and saved on success', async () => {
		const state = new SaveState();
		let sawSavingDuringCall = false;

		const cleanup = $effect.root(() => {
			$effect(() => {
				if (state.saving) sawSavingDuringCall = true;
			});
		});
		flushSync();

		const result = await state.run(async () => {
			flushSync();
		}, 'failed');

		expect(result).toBe(true);
		expect(sawSavingDuringCall).toBe(true);
		expect(state.saving).toBe(false);
		expect(state.saved).toBe(true);
		expect(state.error).toBeNull();
		cleanup();
	});

	it('sets error and leaves saved false on failure', async () => {
		const state = new SaveState();

		const result = await state.run(async () => {
			throw new Error('boom');
		}, 'failed to save');

		expect(result).toBe(false);
		expect(state.saving).toBe(false);
		expect(state.saved).toBe(false);
		expect(state.error).toBe('failed to save');
	});

	it('does not set saved when setSaved is false', async () => {
		const state = new SaveState();

		const result = await state.run(async () => {}, 'failed', { setSaved: false });

		expect(result).toBe(true);
		expect(state.saved).toBe(false);
		expect(state.error).toBeNull();
	});

	it('clears a previous error and saved flag on the next run', async () => {
		const state = new SaveState();

		await state.run(async () => {
			throw new Error('first failure');
		}, 'first error');
		expect(state.error).toBe('first error');

		await state.run(async () => {}, 'second error');
		expect(state.error).toBeNull();
		expect(state.saved).toBe(true);
	});
});
