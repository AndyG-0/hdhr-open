<script lang="ts">
	import { api, type XMLTVFeedChannel, type XMLTVStats } from '$lib/api';
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialUrl: string | null;
		onFeedChannelsChanged: (channels: XMLTVFeedChannel[]) => void;
	}

	let { initialUrl, onFeedChannelsChanged }: Props = $props();

	let xmltvUrlInput = $state('');
	const xmltvState = new SaveState();
	let xmltvStats = $state<XMLTVStats | null>(null);
	let xmltvReloading = $state(false);
	let xmltvReloadMessage = $state<string | null>(null);
	let xmltvReloadError = $state<string | null>(null);

	loadOnceWhen(
		() => initialUrl !== null,
		() => {
			xmltvUrlInput = initialUrl!;
		},
	);

	onMount(() => {
		loadXmltvStats();
	});

	async function loadXmltvStats() {
		try {
			xmltvStats = await api.getXmltvStats();
		} catch {
			// keep stats as null
		}
	}

	async function saveXmltv() {
		xmltvReloadMessage = null;
		xmltvReloadError = null;
		await xmltvState.run(
			async () => {
				await api.updateNetworkIntegration('xmltv', { url: xmltvUrlInput });
				api
					.getXmltvFeedChannels()
					.then(onFeedChannelsChanged)
					.catch(() => {});
				loadXmltvStats();
			},
			get(_)('network_settings.save_error'),
			{ setSaved: false },
		);
	}

	async function reloadXmltv() {
		xmltvReloading = true;
		xmltvReloadMessage = null;
		xmltvReloadError = null;
		try {
			const res = await api.reloadXmltvGuide();
			xmltvStats = res.stats;
			xmltvReloadMessage = get(_)('network_settings.xmltv_reload_success');
			api
				.getXmltvFeedChannels()
				.then(onFeedChannelsChanged)
				.catch(() => {});
		} catch (err) {
			xmltvReloadError = err instanceof Error ? err.message : get(_)('network_settings.xmltv_reload_error');
		} finally {
			xmltvReloading = false;
		}
	}
</script>

<section>
	<h3>{$_('network_settings.section_xmltv')}</h3>
	<label>
		{$_('network_settings.xmltv_url_label')}
		<input type="text" bind:value={xmltvUrlInput} placeholder="http://example.com/guide.xml" />
	</label>
	<p class="hint">{$_('network_settings.xmltv_hint')}</p>

	{#if xmltvState.error}
		<p class="hint error">{xmltvState.error}</p>
	{/if}

	<div class="test-row">
		<button class="save" disabled={xmltvState.saving} onclick={saveXmltv}>
			{xmltvState.saving ? $_('common.saving') : $_('common.save')}
		</button>
		<button type="button" class="test" disabled={xmltvReloading || !xmltvUrlInput.trim()} onclick={reloadXmltv}>
			{xmltvReloading ? $_('network_settings.xmltv_reloading') : $_('network_settings.xmltv_reload_button')}
		</button>
	</div>

	{#if xmltvReloadMessage}
		<p class="hint ok">{xmltvReloadMessage}</p>
	{/if}
	{#if xmltvReloadError}
		<p class="hint error">{xmltvReloadError}</p>
	{/if}

	{#if xmltvStats}
		<div class="stats-panel">
			<h4>{$_('network_settings.xmltv_stats_heading')}</h4>
			<div class="stats-grid">
				<div class="stat-card">
					<span class="stat-label">{$_('network_settings.xmltv_stat_last_refreshed')}</span>
					<span class="stat-value">
						{xmltvStats.last_refreshed_at
							? new Date(xmltvStats.last_refreshed_at).toLocaleString()
							: $_('network_settings.xmltv_stat_never')}
					</span>
				</div>
				<div class="stat-card">
					<span class="stat-label">{$_('network_settings.xmltv_stat_channels')}</span>
					<span class="stat-value">
						{xmltvStats.channels_in_feed > 0 || xmltvStats.mapped_channels_count > 0
							? $_('network_settings.xmltv_stat_channels_detail', {
									values: {
										feed: xmltvStats.channels_in_feed,
										mapped: xmltvStats.mapped_channels_count
									}
								})
							: '0'}
					</span>
				</div>
				<div class="stat-card">
					<span class="stat-label">{$_('network_settings.xmltv_stat_days')}</span>
					<span class="stat-value">
						{xmltvStats.days_count > 0
							? $_('network_settings.xmltv_stat_days_value', {
									values: { count: xmltvStats.days_count }
								})
							: '0'}
					</span>
				</div>
				<div class="stat-card">
					<span class="stat-label">{$_('network_settings.xmltv_stat_dates')}</span>
					<span class="stat-value">
						{xmltvStats.start_date && xmltvStats.end_date
							? `${new Date(xmltvStats.start_date).toLocaleDateString()} – ${new Date(xmltvStats.end_date).toLocaleDateString()}`
							: $_('network_settings.xmltv_stat_no_data')}
					</span>
				</div>
				<div class="stat-card">
					<span class="stat-label">{$_('network_settings.xmltv_stat_programs')}</span>
					<span class="stat-value">
						{xmltvStats.programs_count > 0
							? xmltvStats.programs_count.toLocaleString()
							: '0'}
					</span>
				</div>
			</div>
		</div>
	{/if}
</section>

<style>
	.stats-panel {
		margin-top: 1rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--color-border);
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.stats-panel h4 {
		margin: 0;
		font-size: 0.9rem;
		color: var(--color-text);
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
		gap: 0.75rem;
	}

	.stat-card {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
	}

	.stat-label {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.stat-value {
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--color-text);
		word-break: break-word;
	}
</style>
