<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { HDHomeRunChannel } from '$lib/api';

	interface Props {
		channels: HDHomeRunChannel[];
		favoriteChannels?: Set<string>;
		activeChannels?: Set<string>;
		recordingChannels?: Set<string>;
		currentChannelNumber?: string | null;
		onSelect: (channel: HDHomeRunChannel) => void;
		onClose: () => void;
	}

	let {
		channels,
		favoriteChannels = new Set<string>(),
		activeChannels = new Set<string>(),
		recordingChannels = new Set<string>(),
		currentChannelNumber = null,
		onSelect,
		onClose,
	}: Props = $props();

	let rootEl = $state<HTMLDivElement | null>(null);
	let highlightedIndex = $state(0);

	const orderedChannels = $derived.by(() => {
		const favs = channels.filter((c) => favoriteChannels.has(c.channel_number));
		const rest = channels.filter((c) => !favoriteChannels.has(c.channel_number));
		return [...favs, ...rest];
	});

	$effect(() => {
		const idx = orderedChannels.findIndex((c) => c.channel_number === currentChannelNumber);
		highlightedIndex = idx >= 0 ? idx : 0;
		rootEl?.focus();
	});

	function handleDrawerKeydown(e: KeyboardEvent) {
		if (e.key === 'ArrowDown') {
			e.preventDefault();
			e.stopPropagation();
			highlightedIndex = Math.min(highlightedIndex + 1, orderedChannels.length - 1);
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			e.stopPropagation();
			highlightedIndex = Math.max(highlightedIndex - 1, 0);
		} else if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			e.stopPropagation();
			const target = orderedChannels[highlightedIndex];
			if (target) onSelect(target);
		} else if (e.key === 'Escape') {
			e.preventDefault();
			e.stopPropagation();
			onClose();
		}
	}
</script>

<div class="channel-drawer-backdrop" onclick={onClose} role="presentation">
	<div
		class="channel-drawer"
		bind:this={rootEl}
		tabindex="-1"
		role="dialog"
		aria-label={$_('player.channels', { default: 'Channels' })}
		onclick={(e) => e.stopPropagation()}
		onkeydown={handleDrawerKeydown}
	>
		<div class="drawer-header">
			<span class="drawer-title">{$_('player.channels', { default: 'Channels' })}</span>
			<button
				type="button"
				class="drawer-close-btn"
				onclick={onClose}
				aria-label={$_('player.close', { default: 'Close' })}
			>
				✕
			</button>
		</div>

		{#if orderedChannels.length === 0}
			<div class="empty-channels">
				<p>{$_('hdhomerun.detail.no_channels', { default: 'No channels available' })}</p>
			</div>
		{:else}
			<div class="drawer-list">
				{#each orderedChannels as channel, i (channel.channel_number)}
					<button
						type="button"
						class="channel-row"
						class:current={channel.channel_number === currentChannelNumber}
						class:highlighted={i === highlightedIndex}
						onclick={() => onSelect(channel)}
						onmouseenter={() => (highlightedIndex = i)}
					>
						<span class="favorite-indicator" aria-hidden="true">
							{favoriteChannels.has(channel.channel_number) ? '★' : ''}
						</span>
						<span class="channel-number">{channel.channel_number}</span>
						<span class="channel-info">
							<span class="channel-name-row">
								<span class="channel-name">{channel.name}</span>
								{#if channel.is_hd}<span class="badge">HD</span>{/if}
								{#if recordingChannels.has(channel.channel_number)}
									<span class="badge recording-badge">🔴 Rec</span>
								{:else if activeChannels.has(channel.channel_number)}
									<span class="badge active-badge">Live</span>
								{/if}
							</span>
							{#if channel.now?.title}
								<span class="now-title">{channel.now.title}</span>
							{/if}
						</span>
					</button>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.channel-drawer-backdrop {
		position: fixed;
		inset: 0;
		z-index: 300;
		background: rgba(0, 0, 0, 0.65);
		backdrop-filter: blur(8px);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		box-sizing: border-box;
	}

	.channel-drawer {
		width: 100%;
		max-width: 28rem;
		max-height: 75vh;
		background: rgba(22, 22, 26, 0.98);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 1rem;
		box-shadow: 0 16px 48px rgba(0, 0, 0, 0.85);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		animation: drawer-pop 0.15s ease-out;
	}

	.channel-drawer:focus {
		outline: none;
	}

	.drawer-header {
		padding: 0.85rem 1.25rem;
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		flex-shrink: 0;
	}

	.drawer-title {
		font-size: 0.85rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: rgba(255, 255, 255, 0.7);
	}

	.drawer-close-btn {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.6);
		font-size: 1.1rem;
		cursor: pointer;
		padding: 0.2rem 0.4rem;
		border-radius: 0.25rem;
		line-height: 1;
		transition: color 0.15s ease, background 0.15s ease;
	}

	.drawer-close-btn:hover {
		color: #ffffff;
		background: rgba(255, 255, 255, 0.1);
	}

	.empty-channels {
		padding: 2.5rem 1.5rem;
		text-align: center;
		color: rgba(255, 255, 255, 0.5);
		font-size: 0.9rem;
	}

	.drawer-list {
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		padding: 0.35rem 0;
		max-height: calc(75vh - 3.5rem);
	}

	.channel-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.65rem 1.25rem;
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.85);
		font-size: 0.9rem;
		cursor: pointer;
		text-align: left;
		width: 100%;
		transition: background 0.1s ease;
	}

	.channel-row:hover,
	.channel-row.highlighted {
		background: rgba(255, 255, 255, 0.12);
		color: #ffffff;
	}

	.channel-row.current {
		color: #38bdf8;
		background: rgba(56, 189, 248, 0.15);
	}

	.favorite-indicator {
		width: 1rem;
		flex-shrink: 0;
		color: #38bdf8;
		text-align: center;
		font-size: 0.85rem;
	}

	.channel-number {
		flex-shrink: 0;
		width: 2.75rem;
		font-weight: 700;
		color: #38bdf8;
	}

	.channel-info {
		display: flex;
		flex-direction: column;
		min-width: 0;
		flex: 1;
		gap: 0.15rem;
	}

	.channel-name-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.channel-name {
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.badge {
		font-size: 0.6rem;
		font-weight: 700;
		padding: 0.05rem 0.3rem;
		border-radius: 0.2rem;
		background: rgba(255, 255, 255, 0.18);
		color: rgba(255, 255, 255, 0.85);
		flex-shrink: 0;
	}

	.badge.recording-badge {
		background: rgba(239, 68, 68, 0.25);
		border: 1px solid rgba(239, 68, 68, 0.5);
		color: #fca5a5;
	}

	.badge.active-badge {
		background: rgba(56, 189, 248, 0.2);
		border: 1px solid rgba(56, 189, 248, 0.4);
		color: #7dd3fc;
	}

	.now-title {
		font-size: 0.78rem;
		color: rgba(255, 255, 255, 0.55);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	@keyframes drawer-pop {
		from {
			opacity: 0;
			transform: scale(0.96);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}
</style>
