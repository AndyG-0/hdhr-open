<script lang="ts">
	import { api } from '$lib/api';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialEnabled: string | null;
		initialMaxMinutes: string | null;
	}

	let { initialEnabled, initialMaxMinutes }: Props = $props();

	let enabled = $state(false);
	let maxMinutes = $state(60);
	const sportsExtensionState = new SaveState();

	loadOnceWhen(
		() => initialEnabled !== null && initialMaxMinutes !== null,
		() => {
			enabled = initialEnabled === 'true';
			maxMinutes = Number(initialMaxMinutes) || 60;
		},
	);

	async function saveSportsExtension() {
		await sportsExtensionState.run(async () => {
			await api.updateSettings({
				sports_extension_enabled: enabled ? 'true' : 'false',
				sports_extension_max_minutes: String(Math.max(0, Math.round(maxMinutes))),
			});
		}, 'Could not save sports auto-extend settings.');
	}
</script>

<section>
	<h3>Sports recording auto-extend</h3>
	<label>
		<span class="checkbox-row">
			<input type="checkbox" bind:checked={enabled} />
			Automatically extend recordings that look like live sports if the game hasn't ended on time
		</span>
	</label>
	<label>
		Maximum extension (minutes)
		<input type="number" min="0" step="5" bind:value={maxMinutes} disabled={!enabled} />
	</label>

	{#if sportsExtensionState.error}
		<p class="hint error">{sportsExtensionState.error}</p>
	{/if}
	{#if sportsExtensionState.saved}
		<p class="hint">Saved.</p>
	{/if}
	<button class="save" disabled={sportsExtensionState.saving} onclick={saveSportsExtension}>
		{sportsExtensionState.saving ? 'Saving…' : 'Save sports auto-extend'}
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
