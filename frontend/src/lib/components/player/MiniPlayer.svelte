<script lang="ts">
	import PlayerIcon from './icons/PlayerIcon.svelte';

	interface Props {
		title: string;
		subtitle?: string;
		paused: boolean;
		isVideoLoading?: boolean;
		onTogglePlay: () => void;
		onClose: () => void;
		onExpand: () => void;
	}

	let { title, subtitle, paused, isVideoLoading = false, onTogglePlay, onClose, onExpand }: Props = $props();
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div class="mini-bar" role="button" tabindex="0" onclick={onExpand} onkeydown={(e) => e.key === 'Enter' && onExpand()}>
	<div class="mini-text">
		<span class="mini-title">{title}</span>
		{#if subtitle}<span class="mini-subtitle">{subtitle}</span>{/if}
	</div>
	<div class="mini-controls">
		<button
			type="button"
			class="mini-btn"
			aria-label={paused ? 'Play' : 'Pause'}
			onclick={(e) => {
				e.stopPropagation();
				onTogglePlay();
			}}
		>
			{#if isVideoLoading}
				<span class="mini-spinner" aria-hidden="true"></span>
			{:else}
				<PlayerIcon name={paused ? 'play' : 'pause'} size={16} />
			{/if}
		</button>
		<button
			type="button"
			class="mini-btn"
			aria-label="Expand player"
			onclick={(e) => {
				e.stopPropagation();
				onExpand();
			}}
		>
			<PlayerIcon name="popout" size={14} />
		</button>
		<button
			type="button"
			class="mini-btn"
			aria-label="Close player"
			onclick={(e) => {
				e.stopPropagation();
				onClose();
			}}
		>
			✕
		</button>
	</div>
</div>

<style>
	.mini-bar {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		padding: 0.5rem;
		background: linear-gradient(to top, rgba(0, 0, 0, 0.85), rgba(0, 0, 0, 0.15) 60%, transparent);
		color: #fff;
		cursor: pointer;
	}

	.mini-text {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
		overflow: hidden;
	}

	.mini-title {
		font-size: 0.8rem;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.mini-subtitle {
		font-size: 0.7rem;
		opacity: 0.75;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.mini-controls {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 0.35rem;
	}

	.mini-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		border: none;
		border-radius: 50%;
		background: rgba(255, 255, 255, 0.15);
		color: #fff;
		font-size: 0.75rem;
		cursor: pointer;
	}

	.mini-btn:hover {
		background: rgba(255, 255, 255, 0.3);
	}

	.mini-spinner {
		width: 0.9rem;
		height: 0.9rem;
		border: 2px solid rgba(255, 255, 255, 0.35);
		border-top-color: #fff;
		border-radius: 50%;
		animation: mini-spin 0.8s linear infinite;
	}

	@keyframes mini-spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
