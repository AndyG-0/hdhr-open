<script lang="ts">
	import { api } from '$lib/api';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialEnabled: string | null;
	}

	let { initialEnabled }: Props = $props();

	let enabled = $state(true);
	const posterBackfillState = new SaveState();

	loadOnceWhen(
		() => initialEnabled !== null,
		() => {
			enabled = initialEnabled === 'true';
		},
	);

	async function savePosterBackfill() {
		await posterBackfillState.run(async () => {
			await api.updateSettings({
				poster_backfill_enabled: enabled ? 'true' : 'false',
			});
		}, 'Could not save Poster Backfill settings.');
	}
</script>

<section>
	<h3>Poster Backfill</h3>
	<label>
		<span class="checkbox-row">
			<input type="checkbox" bind:checked={enabled} />
			Look up missing show/movie/sports artwork from TMDb and TheSportsDB when the guide refreshes
			or Discovery loads
		</span>
	</label>

	{#if posterBackfillState.error}
		<p class="hint error">{posterBackfillState.error}</p>
	{/if}
	{#if posterBackfillState.saved}
		<p class="hint">Saved.</p>
	{/if}
	<button class="save" disabled={posterBackfillState.saving} onclick={savePosterBackfill}>
		{posterBackfillState.saving ? 'Saving…' : 'Save Poster Backfill'}
	</button>
</section>

<style>
	.checkbox-row {
		flex-direction: row;
		align-items: center;
		gap: 0.5rem;
		display: flex;
	}

	.checkbox-row input {
		width: auto;
	}
</style>
