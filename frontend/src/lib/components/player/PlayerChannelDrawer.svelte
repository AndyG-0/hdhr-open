<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { HDHomeRunChannel } from '$lib/api';

	interface Props {
		channels: HDHomeRunChannel[];
		favoriteChannels?: Set<string>;
		currentChannelNumber?: string | null;
		onSelect: (channel: HDHomeRunChannel) => void;
		onClose: () => void;
	}

	let {
		channels,
		favoriteChannels = new Set<string>(),
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
		<div class="drawer-header">{$_('player.channels', { default: 'Channels' })}</div>
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
						</span>
						{#if channel.now?.title}
							<span class="now-title">{channel.now.title}</span>
						{/if}
					</span>
				</button>
			{/each}
		</div>
	</div>
</div>

<style>
	.channel-drawer-backdrop {
		position: absolute;
		inset: 0;
		z-index: 170;
		background: rgba(0, 0, 0, 0.55);
		display: flex;
		align-items: flex-end;
		justify-content: center;
		padding: 0 1rem 1rem;
	}

	.channel-drawer {
		width: 100%;
		max-width: 26rem;
		max-height: 65vh;
		background: rgba(22, 22, 26, 0.96);
		backdrop-filter: blur(16px);
		border: 1px solid rgba(255, 255, 255, 0.15);
		border-radius: 0.75rem 0.75rem 0.5rem 0.5rem;
		box-shadow: 0 12px 36px rgba(0, 0, 0, 0.75);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		animation: drawer-slide-up 0.2s ease-out;
	}

	.channel-drawer:focus {
		outline: none;
	}

	.drawer-header {
		padding: 0.75rem 1rem;
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: rgba(255, 255, 255, 0.55);
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		flex-shrink: 0;
	}

	.drawer-list {
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		padding: 0.25rem 0;
	}

	.channel-row {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.55rem 1rem;
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.85);
		font-size: 0.9rem;
		cursor: pointer;
		text-align: left;
		width: 100%;
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
	}

	.channel-number {
		flex-shrink: 0;
		width: 2.5rem;
		font-weight: 600;
		opacity: 0.8;
	}

	.channel-info {
		display: flex;
		flex-direction: column;
		min-width: 0;
		flex: 1;
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

	.now-title {
		font-size: 0.78rem;
		color: rgba(255, 255, 255, 0.55);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	@keyframes drawer-slide-up {
		from {
			opacity: 0;
			transform: translateY(100%);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
</style>
