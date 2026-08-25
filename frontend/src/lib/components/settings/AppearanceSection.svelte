<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { theme, persistTheme } from '$lib/stores/theme';
	import { SaveState } from '$lib/save-state.svelte';

	// Fallback matches the backend's default set; refreshed from /api/theme
	// on mount so new themes show up without a frontend redeploy.
	let themeIds = $state(['light', 'dark', 'sepia', 'contrast', 'forest', 'ocean']);
	let themeNames = $state<Record<string, string>>({});

	// Theme applies live to the DOM the instant the store is set (see
	// stores/theme.ts) — that live-preview stays, but the server write
	// (persistTheme) waits for Save like every other section on this page,
	// rather than firing on every selection.
	const themeState = new SaveState();

	async function saveTheme() {
		await themeState.run(async () => {
			await persistTheme($theme);
		}, get(_)('settings.appearance.save_error'));
	}

	onMount(async () => {
		try {
			const { themes } = await api.themes();
			themeIds = themes.map((t) => t.id);
			themeNames = Object.fromEntries(themes.map((t) => [t.id, t.name]));
		} catch {
			// keep the fallback list
		}
	});
</script>

<section>
	<h3>{$_('settings.appearance.title')}</h3>
	<select
		aria-label={$_('settings.appearance.title')}
		value={$theme}
		onchange={(e) => {
			theme.set(e.currentTarget.value);
			themeState.saved = false;
		}}
	>
		{#each themeIds as id (id)}
			<option value={id}>{themeNames[id] ?? id}</option>
		{/each}
	</select>

	{#if themeState.error}
		<p class="hint error">{themeState.error}</p>
	{/if}
	{#if themeState.saved}
		<p class="hint">{$_('common.saved')}</p>
	{/if}
	<button class="save" disabled={themeState.saving} onclick={saveTheme}>
		{themeState.saving ? $_('common.saving') : $_('settings.appearance.save')}
	</button>
</section>
