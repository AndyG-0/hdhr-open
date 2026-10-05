<script lang="ts">
	import { api } from '$lib/api';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialMode: string | null;
	}

	let { initialMode }: Props = $props();

	let mode = $state<'all' | 'none' | 'per_rule'>('all');
	const comskipState = new SaveState();

	loadOnceWhen(
		() => initialMode !== null,
		() => {
			mode = initialMode === 'none' || initialMode === 'per_rule' ? initialMode : 'all';
		},
	);

	async function saveComskip() {
		await comskipState.run(async () => {
			await api.updateSettings({ comskip_mode: mode });
		}, 'Could not save commercial detection settings.');
	}
</script>

<section>
	<h3>Commercial detection</h3>
	<p class="hint">
		Runs comskip against completed recordings to mark commercial breaks for skip-ahead during
		playback. Applies to Built-in DVR recordings, and to HDHomeRun DVR recordings once a local
		recordings path is configured under HDHomeRun network settings.
	</p>
	<label class="radio-row">
		<input type="radio" name="comskip-mode" value="all" bind:group={mode} />
		Always detect commercials
	</label>
	<label class="radio-row">
		<input type="radio" name="comskip-mode" value="none" bind:group={mode} />
		Never detect commercials
	</label>
	<label class="radio-row">
		<input type="radio" name="comskip-mode" value="per_rule" bind:group={mode} />
		Let each recording decide
	</label>

	{#if comskipState.error}
		<p class="hint error">{comskipState.error}</p>
	{/if}
	{#if comskipState.saved}
		<p class="hint">Saved.</p>
	{/if}
	<button class="save" disabled={comskipState.saving} onclick={saveComskip}>
		{comskipState.saving ? 'Saving…' : 'Save commercial detection'}
	</button>
</section>

<style>
	.radio-row {
		flex-direction: row;
		align-items: center;
		gap: 0.5rem;
		display: flex;
	}

	.radio-row input {
		width: auto;
	}
</style>
