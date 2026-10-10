<script lang="ts">
	import { api } from '$lib/api';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialEnabled: string | null;
	}

	let { initialEnabled }: Props = $props();

	let enabled = $state(false);
	const discoveryState = new SaveState();

	loadOnceWhen(
		() => initialEnabled !== null,
		() => {
			enabled = initialEnabled === 'true';
		},
	);

	async function saveDiscovery() {
		await discoveryState.run(async () => {
			await api.updateSettings({
				discovery_enabled: enabled ? 'true' : 'false',
			});
		}, 'Could not save Discovery settings.');
	}
</script>

<section>
	<h3>Discovery</h3>
	<label>
		<span class="checkbox-row">
			<input type="checkbox" bind:checked={enabled} />
			Show a Discovery tab with upcoming shows recommended from your recording history
		</span>
	</label>

	{#if discoveryState.error}
		<p class="hint error">{discoveryState.error}</p>
	{/if}
	{#if discoveryState.saved}
		<p class="hint">Saved.</p>
	{/if}
	<button class="save" disabled={discoveryState.saving} onclick={saveDiscovery}>
		{discoveryState.saving ? 'Saving…' : 'Save Discovery'}
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
