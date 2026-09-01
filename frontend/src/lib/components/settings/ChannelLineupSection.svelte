<script lang="ts">
	import { api, type HDHomeRunChannelSetting, type XMLTVFeedChannel, type SchedulesDirectStation } from '$lib/api';
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';

	interface Props {
		xmltvFeedChannels: XMLTVFeedChannel[];
		sdStations: SchedulesDirectStation[];
		onFeedChannelsChanged: (channels: XMLTVFeedChannel[]) => void;
		onStationsChanged: (stations: SchedulesDirectStation[]) => void;
	}

	let { xmltvFeedChannels, sdStations, onFeedChannelsChanged, onStationsChanged }: Props = $props();

	let channelSettings = $state<HDHomeRunChannelSetting[]>([]);
	let channelSettingsLoading = $state(false);
	let channelSettingsError = $state<string | null>(null);
	let channelSavingId = $state<string | null>(null);
	let channelSavedId = $state<string | null>(null);
	let guideRefreshing = $state(false);
	let guideRefreshMessage = $state<string | null>(null);
	let guideRefreshError = $state<string | null>(null);

	onMount(() => {
		loadChannelSettings();
	});

	async function loadChannelSettings() {
		channelSettingsLoading = true;
		channelSettingsError = null;
		try {
			const [channels, feedChannels, schedulesDirectStations] = await Promise.all([
				api.getChannelSettings().catch(() => []),
				api.getXmltvFeedChannels().catch(() => []),
				api.getSchedulesDirectStations().catch(() => []),
			]);
			channelSettings = channels;
			onFeedChannelsChanged(feedChannels);
			onStationsChanged(schedulesDirectStations);
		} catch {
			channelSettingsError = get(_)('network_settings.channel_save_error');
		} finally {
			channelSettingsLoading = false;
		}
	}

	async function saveChannelSetting(channel: HDHomeRunChannelSetting) {
		channelSavingId = channel.id;
		channelSavedId = null;
		channelSettingsError = null;
		try {
			const updated = await api.updateChannelSetting(channel.id, {
				guide_provider: channel.guide_provider,
				xmltv_channel_id: channel.xmltv_channel_id,
				xmltv_display_name: channel.xmltv_display_name,
				sd_station_id: channel.sd_station_id,
				sd_lineup_id: channel.sd_lineup_id,
				is_favorite: channel.is_favorite,
				hidden: channel.hidden,
			});
			channelSettings = channelSettings.map((c) => (c.id === channel.id ? updated : c));
			channelSavedId = channel.id;
			setTimeout(() => {
				if (channelSavedId === channel.id) channelSavedId = null;
			}, 2500);
		} catch {
			channelSettingsError = get(_)('network_settings.channel_save_error');
		} finally {
			channelSavingId = null;
		}
	}

	async function clearXmltvMapping(channel: HDHomeRunChannelSetting) {
		channel.xmltv_channel_id = '';
		channel.xmltv_display_name = '';
		await saveChannelSetting(channel);
	}

	async function clearSdMapping(channel: HDHomeRunChannelSetting) {
		channel.sd_station_id = '';
		channel.sd_lineup_id = '';
		await saveChannelSetting(channel);
	}

	async function handleRefreshGuide() {
		guideRefreshing = true;
		guideRefreshMessage = null;
		guideRefreshError = null;
		try {
			await api.refreshGuide();
			guideRefreshMessage = get(_)('network_settings.refresh_guide_success');
			await loadChannelSettings();
		} catch {
			guideRefreshError = get(_)('network_settings.refresh_guide_error');
		} finally {
			guideRefreshing = false;
		}
	}
</script>

<section class="channel-lineup-section">
	<div class="section-header-row">
		<div>
			<h3>{$_('network_settings.channel_mapping_heading')}</h3>
			<p class="hint">{$_('network_settings.channel_mapping_hint')}</p>
		</div>
		<button type="button" class="test" disabled={guideRefreshing} onclick={handleRefreshGuide}>
			{guideRefreshing ? $_('network_settings.refreshing_guide') : $_('network_settings.refresh_guide')}
		</button>
	</div>

	{#if guideRefreshMessage}
		<p class="hint ok">{guideRefreshMessage}</p>
	{/if}
	{#if guideRefreshError}
		<p class="hint error">{guideRefreshError}</p>
	{/if}
	{#if channelSettingsError}
		<p class="hint error">{channelSettingsError}</p>
	{/if}

	{#if channelSettingsLoading && channelSettings.length === 0}
		<p class="hint">{$_('common.loading')}</p>
	{:else if channelSettings.length === 0}
		<p class="hint">{$_('network_settings.no_channels')}</p>
	{:else}
		{#if xmltvFeedChannels.length > 0}
			<datalist id="xmltv-feed-channels-list">
				{#each xmltvFeedChannels as feedCh (feedCh.xmltv_channel_id)}
					<option value={feedCh.xmltv_channel_id}>
						{feedCh.display_names.length > 0 ? feedCh.display_names.join(' / ') : feedCh.xmltv_channel_id}
					</option>
				{/each}
			</datalist>
		{/if}

		{#if sdStations.length > 0}
			<datalist id="sd-stations-list">
				{#each sdStations as st (st.station_id + st.lineup_id)}
					<option value={st.station_id}>
						{st.callsign ? `${st.callsign} (${st.name})` : st.name} - {st.channel_number || ''} [{st.lineup_id}]
					</option>
				{/each}
			</datalist>
		{/if}

		<div class="channel-settings-list">
			{#each channelSettings as channel (channel.id)}
				<div class="channel-setting-card">
					<div class="channel-header-row">
						<span class="channel-badge">{channel.channel_number}</span>
						<span class="channel-name">{channel.name}</span>
						{#if channel.is_hd}
							<span class="hd-badge">HD</span>
						{/if}
					</div>

					<div class="channel-fields-grid">
						<label>
							{$_('network_settings.guide_provider_label')}
							<select bind:value={channel.guide_provider}>
								<option value={null}>{$_('network_settings.guide_provider_default')}</option>
								<option value="hdhomerun_cloud">{$_('network_settings.guide_provider_hdhomerun')}</option>
								<option value="xmltv">{$_('network_settings.guide_provider_xmltv')}</option>
								<option value="schedules_direct">{$_('network_settings.guide_provider_schedules_direct')}</option>
							</select>
						</label>

						{#if channel.guide_provider === 'xmltv' || channel.guide_provider === null}
							<label>
								{$_('network_settings.xmltv_id_label')}
								<input
									type="text"
									list="xmltv-feed-channels-list"
									bind:value={channel.xmltv_channel_id}
									placeholder={$_('network_settings.xmltv_id_placeholder')}
								/>
							</label>

							<label>
								{$_('network_settings.xmltv_name_label')}
								<input
									type="text"
									bind:value={channel.xmltv_display_name}
									placeholder={$_('network_settings.xmltv_name_placeholder')}
								/>
							</label>
						{/if}

						{#if channel.guide_provider === 'schedules_direct' || channel.guide_provider === null}
							<label>
								{$_('network_settings.sd_station_id_label')}
								<input
									type="text"
									list="sd-stations-list"
									bind:value={channel.sd_station_id}
									placeholder={$_('network_settings.sd_station_id_placeholder')}
								/>
							</label>
						{/if}
					</div>

					<div class="channel-actions-row">
						<button
							type="button"
							class="save small"
							disabled={channelSavingId === channel.id}
							onclick={() => saveChannelSetting(channel)}
						>
							{channelSavingId === channel.id ? $_('common.saving') : $_('common.save')}
						</button>
						{#if channel.xmltv_channel_id}
							<button
								type="button"
								class="clear"
								disabled={channelSavingId === channel.id}
								onclick={() => clearXmltvMapping(channel)}
							>
								{$_('network_settings.clear_mapping')}
							</button>
						{/if}
						{#if channel.sd_station_id}
							<button
								type="button"
								class="clear"
								disabled={channelSavingId === channel.id}
								onclick={() => clearSdMapping(channel)}
							>
								{$_('network_settings.clear_sd_mapping')}
							</button>
						{/if}
						{#if channelSavedId === channel.id}
							<span class="hint ok">{$_('network_settings.channel_saved')}</span>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</section>

<style>
	.channel-settings-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		margin-top: 0.5rem;
		max-height: 40rem;
		overflow-y: auto;
		padding-right: 0.25rem;
	}

	.channel-setting-card {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.75rem;
	}

	.channel-header-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.channel-badge {
		font-weight: 700;
		color: var(--color-accent);
		font-size: 0.95rem;
	}

	.channel-name {
		font-weight: 600;
		font-size: 0.9rem;
	}

	.hd-badge {
		font-size: 0.7rem;
		background: var(--color-border);
		color: var(--color-text-muted);
		border-radius: 0.25rem;
		padding: 0.1rem 0.35rem;
		font-weight: 600;
	}

	.channel-fields-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.5rem;
	}

	@media (min-width: 600px) {
		.channel-fields-grid {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.channel-fields-grid label {
		min-width: 0;
	}

	.channel-fields-grid input,
	.channel-fields-grid select {
		width: 100%;
		min-width: 0;
	}

	.channel-actions-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 0.25rem;
	}
</style>
