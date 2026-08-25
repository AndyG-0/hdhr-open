<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { locale, persistLocale } from '$lib/i18n';
	import { SaveState } from '$lib/save-state.svelte';

	const localeState = new SaveState();

	async function saveLocale() {
		await localeState.run(async () => {
			await persistLocale($locale ?? 'en');
		}, get(_)('settings.language.save_error'));
	}
</script>

<section>
	<h3>{$_('settings.language.title')}</h3>
	<select
		aria-label={$_('settings.language.title')}
		value={$locale}
		onchange={(e) => {
			locale.set(e.currentTarget.value);
			localeState.saved = false;
		}}
	>
		<option value="en">English</option>
		<option value="es">Español</option>
		<option value="fr">Français</option>
		<option value="de">Deutsch</option>
	</select>

	{#if localeState.error}
		<p class="hint error">{localeState.error}</p>
	{/if}
	{#if localeState.saved}
		<p class="hint">{$_('common.saved')}</p>
	{/if}
	<button class="save" disabled={localeState.saving} onclick={saveLocale}>
		{localeState.saving ? $_('common.saving') : $_('settings.language.save')}
	</button>
</section>
