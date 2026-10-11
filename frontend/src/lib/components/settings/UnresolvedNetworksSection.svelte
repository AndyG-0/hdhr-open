<script lang="ts">
	import { api, type UnresolvedNetwork, type HDHomeRunChannelSetting } from '$lib/api';
	import { onMount } from 'svelte';

	let unresolved = $state<UnresolvedNetwork[]>([]);
	let channels = $state<HDHomeRunChannelSetting[]>([]);
	let selectedChannelByNetwork = $state<Record<string, string>>({});
	let assigningNetwork = $state<string | null>(null);
	let watchLinkByNetwork = $state<Record<string, string>>({});
	let savingWatchLinkNetwork = $state<string | null>(null);
	let error = $state<string | null>(null);

	onMount(() => {
		load();
	});

	async function load() {
		error = null;
		try {
			const [unresolvedRes, channelsRes] = await Promise.all([
				api.getUnresolvedSportsNetworks(),
				api.getChannelSettings(),
			]);
			unresolved = unresolvedRes.unresolved_networks;
			channels = channelsRes;
			watchLinkByNetwork = Object.fromEntries(unresolved.map((n) => [n.network_name, n.custom_watch_url ?? '']));
		} catch {
			error = 'Could not load unresolved broadcast networks.';
		}
	}

	async function assignChannel(networkName: string) {
		const channelId = selectedChannelByNetwork[networkName];
		if (!channelId) return;
		assigningNetwork = networkName;
		error = null;
		try {
			await api.saveSportsNetworkMapEntry(networkName, channelId);
			unresolved = unresolved.filter((n) => n.network_name !== networkName);
		} catch {
			error = 'Could not map this broadcast network.';
		} finally {
			assigningNetwork = null;
		}
	}

	async function saveWatchLink(networkName: string) {
		const url = (watchLinkByNetwork[networkName] ?? '').trim();
		savingWatchLinkNetwork = networkName;
		error = null;
		try {
			if (url) {
				await api.saveSportsNetworkWatchLink(networkName, url);
			} else {
				await api.deleteSportsNetworkWatchLink(networkName);
			}
			// Reload rather than patching local state - the effective watch_url
			// is a server-computed merge of this custom link and the curated
			// well-known-network default, which we don't have locally.
			await load();
		} catch {
			error = 'Could not save the watch link for this network.';
		} finally {
			savingWatchLinkNetwork = null;
		}
	}

	function formatGameTime(startTs: number): string {
		return new Date(startTs * 1000).toLocaleString([], {
			weekday: 'short',
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		});
	}
</script>

<section>
	<h3>Unresolved broadcast networks</h3>
	<p class="hint">
		These broadcast networks are airing games for your favorited teams but aren't mapped to a channel yet, so those
		games can't be recorded automatically until you assign one.
	</p>

	{#if error}
		<p class="hint error">{error}</p>
	{/if}

	{#if unresolved.length === 0}
		<p class="hint">No unresolved broadcast networks.</p>
	{:else}
		<ul class="unresolved-networks-list">
			{#each unresolved as network (network.network_name)}
				<li class="unresolved-network-item">
					<div class="unresolved-network-header">
						<span class="network-name">{network.network_name}</span>
						{#if network.is_ota}
							<span class="ota-badge">Over-the-air</span>
						{:else if network.watch_url}
							<a class="watch-link" href={network.watch_url} target="_blank" rel="noopener noreferrer">Watch ↗</a>
						{/if}
					</div>

					{#if network.is_ota}
						<p class="hint">
							No local {network.network_name} affiliate was found in your channel lineup, so this couldn't be auto-matched.
							Run a guide refresh if you've just set up your HDHomeRun tuner, or assign a channel manually below.
						</p>
					{:else}
						<p class="hint">
							{network.network_name} isn't an over-the-air network, so it requires a manual channel mapping.
						</p>
					{/if}

					{#if !network.is_ota}
						<span class="unresolved-network-watch-link">
							<input
								type="text"
								placeholder="Custom watch link (e.g. https://example.com/watch)"
								bind:value={watchLinkByNetwork[network.network_name]}
							/>
							<button
								type="button"
								class="save small"
								disabled={savingWatchLinkNetwork === network.network_name}
								onclick={() => saveWatchLink(network.network_name)}
							>
								Save link
							</button>
						</span>
					{/if}

					<ul class="unresolved-games-list">
						{#each network.games as game (game.espn_event_id)}
							<li>
								<span class="game-title">{game.matchup_title ?? 'Upcoming game'}</span>
								<span class="game-time">{formatGameTime(game.start_ts)}</span>
							</li>
						{/each}
					</ul>

					<span class="unresolved-network-assign">
						<select bind:value={selectedChannelByNetwork[network.network_name]}>
							<option value="">Select a channel…</option>
							{#each channels as channel (channel.id)}
								<option value={channel.id}>{channel.channel_number} {channel.name}</option>
							{/each}
						</select>
						<button
							type="button"
							class="save small"
							disabled={!selectedChannelByNetwork[network.network_name] || assigningNetwork === network.network_name}
							onclick={() => assignChannel(network.network_name)}
						>
							Assign
						</button>
					</span>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.unresolved-networks-list {
		list-style: none;
		margin: 0.75rem 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.unresolved-network-item {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		padding: 0.5rem 0.65rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.35rem;
		font-size: 0.85rem;
	}

	.unresolved-network-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.network-name {
		font-weight: 600;
	}

	.ota-badge {
		font-size: 0.7rem;
		background: var(--color-border);
		color: var(--color-text-muted);
		border-radius: 0.25rem;
		padding: 0.1rem 0.35rem;
		font-weight: 600;
	}

	.unresolved-games-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.unresolved-games-list li {
		display: flex;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.unresolved-network-assign {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.watch-link {
		font-size: 0.75rem;
		color: var(--color-accent);
	}

	.unresolved-network-watch-link {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.unresolved-network-watch-link input {
		flex: 1;
		min-width: 0;
	}
</style>
