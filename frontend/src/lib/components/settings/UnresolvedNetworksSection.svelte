<script lang="ts">
	import { api, type UnresolvedNetwork, type HDHomeRunChannelSetting } from '$lib/api';
	import { onMount } from 'svelte';

	let unresolved = $state<UnresolvedNetwork[]>([]);
	let channels = $state<HDHomeRunChannelSetting[]>([]);
	let selectedChannelByNetwork = $state<Record<string, string>>({});
	let assigningNetwork = $state<string | null>(null);
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
					<span>
						{network.network_name}
						({network.upcoming_count} upcoming {network.upcoming_count === 1 ? 'game' : 'games'})
					</span>
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
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
		padding: 0.35rem 0.5rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.35rem;
		font-size: 0.85rem;
	}

	.unresolved-network-assign {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}
</style>
