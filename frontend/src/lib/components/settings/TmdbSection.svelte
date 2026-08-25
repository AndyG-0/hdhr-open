<script lang="ts">
	import { api } from '$lib/api';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialHasApiKey: boolean | null;
	}

	let { initialHasApiKey }: Props = $props();

	let tmdbApiKeyInput = $state('');
	let tmdbHasApiKey = $state(false);
	const tmdbState = new SaveState();

	loadOnceWhen(
		() => initialHasApiKey !== null,
		() => {
			tmdbHasApiKey = initialHasApiKey ?? false;
		},
	);

	async function saveTmdb() {
		await tmdbState.run(
			async () => {
				const payload: Record<string, unknown> = {};
				if (tmdbApiKeyInput) {
					payload.api_key = tmdbApiKeyInput;
				}
				const res = await api.updateNetworkIntegration('tmdb', payload);
				tmdbHasApiKey = Boolean(res.settings.has_api_key);
				tmdbApiKeyInput = '';
			},
			get(_)('network_settings.save_error'),
			{ setSaved: false },
		);
	}
</script>

<section>
	<h3>{$_('network_settings.section_tmdb')}</h3>
	<p class="hint">{$_('network_settings.tmdb_hint')}</p>

	<label>
		{$_('network_settings.tmdb_api_key_label')}
		<input type="password" bind:value={tmdbApiKeyInput} placeholder={tmdbHasApiKey ? '(unchanged)' : ''} />
	</label>

	<p class="hint">
		<a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noopener noreferrer">
			{$_('network_settings.tmdb_get_key_link')}
		</a>
	</p>

	{#if tmdbState.error}
		<p class="hint error">{tmdbState.error}</p>
	{/if}

	<button class="save" disabled={tmdbState.saving} onclick={saveTmdb}>
		{tmdbState.saving ? $_('common.saving') : $_('common.save')}
	</button>

	<p class="hint">{$_('network_settings.tmdb_attribution')}</p>
</section>
