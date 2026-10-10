<script lang="ts">
	import { api, type HDHomeRunChannel, type HDHomeRunGuideEntry, type RecordingRuleOptions } from '$lib/api';
	import DiscoveryCard from '$lib/components/DiscoveryCard.svelte';
	import HDHomeRunRecordingOptionsDialog from '$lib/components/details/HDHomeRunRecordingOptionsDialog.svelte';
	import { buildEpisodeRulePayload, buildSeriesRulePayload } from '$lib/recording-rule-actions';
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';

	let loading = $state(true);
	let hasProfile = $state(false);
	let items = $state<HDHomeRunGuideEntry[]>([]);
	let channels = $state<HDHomeRunChannel[]>([]);
	let officialDvrActive = $state(false);
	let error = $state<string | null>(null);
	let recordingLoading = $state<string | null>(null);
	let selectedAiring = $state<HDHomeRunGuideEntry | null>(null);

	function channelFor(channelNumber?: string | null): HDHomeRunChannel | null {
		if (!channelNumber) return null;
		return channels.find((c) => c.channel_number === channelNumber) ?? null;
	}

	async function load() {
		loading = true;
		try {
			const result = await api.getDiscovery();
			hasProfile = result.has_profile;
			items = result.items;
		} catch {
			items = [];
		} finally {
			loading = false;
		}
	}

	async function loadChannels() {
		try {
			const result = await api.getHDHomeRunChannels();
			channels = result.channels;
		} catch {
			channels = [];
		}
	}

	async function loadDvrInfo() {
		try {
			const info = await api.getDvrInfo();
			officialDvrActive = info.is_builtin === false;
		} catch {
			officialDvrActive = false;
		}
	}

	onMount(() => {
		load();
		loadChannels();
		loadDvrInfo();
	});

	async function recordEpisode(options: RecordingRuleOptions) {
		if (!selectedAiring) return;
		const targetId = selectedAiring.series_id || selectedAiring.title;
		error = null;
		recordingLoading = targetId;
		try {
			const payload = buildEpisodeRulePayload(
				selectedAiring.series_id,
				selectedAiring.channel_number,
				selectedAiring.start,
				options,
			);
			await api.addHDHomeRunRecordingRule(payload);
			selectedAiring = null;
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function recordSeries(options: RecordingRuleOptions) {
		if (!selectedAiring) return;
		const targetId = selectedAiring.series_id || selectedAiring.title;
		error = null;
		recordingLoading = targetId;
		try {
			const payload = buildSeriesRulePayload(selectedAiring.series_id, selectedAiring.channel_number, options);
			await api.addHDHomeRunRecordingRule(payload);
			selectedAiring = null;
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}
</script>

<div class="discovery-page">
	{#if loading}
		<p class="hint">{$_('common.loading')}</p>
	{:else}
		{#if error}
			<p class="hint error">{error}</p>
		{/if}
		{#if !hasProfile && items.length > 0}
			<div class="banner notice">{$_('discovery.fallback_banner')}</div>
		{/if}
		{#if items.length === 0}
			<p class="hint">{$_('discovery.empty')}</p>
		{:else}
			<div class="discovery-grid">
				{#each items as airing, i (`${airing.series_id ?? airing.title}-${airing.channel_number}-${airing.start}-${i}`)}
					<DiscoveryCard {airing} onSelect={() => (selectedAiring = airing)} />
				{/each}
			</div>
		{/if}
	{/if}
</div>

{#if selectedAiring}
	{@const channel = channelFor(selectedAiring.channel_number)}
	<HDHomeRunRecordingOptionsDialog
		airing={selectedAiring}
		channelName={channel?.name ?? ''}
		channelNumber={selectedAiring.channel_number ?? ''}
		{channels}
		isHd={channel?.is_hd ?? false}
		canRecordSeries={!!(selectedAiring.series_id || selectedAiring.title)}
		{officialDvrActive}
		loading={recordingLoading === (selectedAiring.series_id || selectedAiring.title)}
		onConfirm={(mode, options) => {
			if (mode === 'series') {
				recordSeries(options);
			} else {
				recordEpisode(options);
			}
		}}
		onClose={() => (selectedAiring = null)}
	/>
{/if}

<style>
	.discovery-page {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
		gap: 0.75rem;
		padding: 1rem;
		overflow-y: auto;
	}

	.discovery-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
		gap: 0.75rem;
	}

	.banner.notice {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.6rem 0.85rem;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.hint {
		color: var(--color-text-muted);
		margin: 0;
		font-size: 0.9rem;
	}

	.hint.error {
		color: var(--color-error);
	}
</style>
