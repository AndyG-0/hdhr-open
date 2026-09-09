<script lang="ts">
	import { _ } from 'svelte-i18n';
	import PlayerIcon from '../icons/PlayerIcon.svelte';

	interface Props {
		slotIndex: number;
		onAddFeed: () => void;
	}

	let { slotIndex, onAddFeed }: Props = $props();
</script>

<div class="empty-tile" role="region" aria-label="Empty multi-view slot">
	<button
		type="button"
		class="add-feed-button"
		onclick={onAddFeed}
		aria-label={$_('multiview.add_feed', { default: 'Add Feed' })}
	>
		<div class="icon-circle">
			<PlayerIcon name="plus" size={32} />
		</div>
		<span class="btn-label">{$_('multiview.add_feed', { default: 'Add Feed' })}</span>
		<span class="slot-num-hint">Slot {slotIndex + 1}</span>
	</button>
</div>

<style>
	.empty-tile {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 200px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(255, 255, 255, 0.03);
		border: 2px dashed rgba(255, 255, 255, 0.2);
		border-radius: 1rem;
		overflow: hidden;
		transition: border-color 0.2s ease, background-color 0.2s ease;
	}

	.empty-tile:hover {
		border-color: rgba(56, 189, 248, 0.5);
		background: rgba(56, 189, 248, 0.05);
	}

	.add-feed-button {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.75rem;
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.75);
		cursor: pointer;
		padding: 2rem;
		width: 100%;
		height: 100%;
		border-radius: 1rem;
		transition: transform 0.15s ease, color 0.15s ease;
	}

	.add-feed-button:hover {
		color: #ffffff;
		transform: scale(1.02);
	}

	.icon-circle {
		width: 3.5rem;
		height: 3.5rem;
		border-radius: 50%;
		background: rgba(255, 255, 255, 0.1);
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background 0.2s ease;
	}

	.add-feed-button:hover .icon-circle {
		background: rgba(56, 189, 248, 0.3);
		color: #38bdf8;
	}

	.btn-label {
		font-size: 1.05rem;
		font-weight: 600;
		letter-spacing: 0.01em;
	}

	.slot-num-hint {
		font-size: 0.75rem;
		color: rgba(255, 255, 255, 0.4);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
</style>
