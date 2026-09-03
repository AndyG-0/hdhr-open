<script lang="ts">
	import { _ } from 'svelte-i18n';
	import PlayerIcon from './icons/PlayerIcon.svelte';

	interface Props {
		volume: number;
		muted: boolean;
		onVolumeChange: (vol: number) => void;
		onMuteToggle: () => void;
	}

	let { volume = 1, muted = false, onVolumeChange, onMuteToggle }: Props = $props();

	let sliderEl = $state<HTMLDivElement | null>(null);
	let isDragging = $state(false);

	const iconName = $derived.by<
		'volume-muted' | 'volume-low' | 'volume-medium' | 'volume-high'
	>(() => {
		if (muted || volume === 0) return 'volume-muted';
		if (volume < 0.33) return 'volume-low';
		if (volume < 0.67) return 'volume-medium';
		return 'volume-high';
	});

	const displayPercent = $derived(muted ? 0 : Math.round(volume * 100));

	function handlePointerDown(e: PointerEvent) {
		isDragging = true;
		(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
		updateFromPointer(e);
	}

	function handlePointerMove(e: PointerEvent) {
		if (!isDragging) return;
		updateFromPointer(e);
	}

	function handlePointerUp(e: PointerEvent) {
		if (!isDragging) return;
		isDragging = false;
		try {
			(e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
		} catch {
			// ignore
		}
	}

	function updateFromPointer(e: PointerEvent) {
		if (!sliderEl) return;
		const rect = sliderEl.getBoundingClientRect();
		const fraction = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
		onVolumeChange(fraction);
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
			e.preventDefault();
			onVolumeChange(Math.min(1, volume + 0.05));
		} else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
			e.preventDefault();
			onVolumeChange(Math.max(0, volume - 0.05));
		}
	}
</script>

<div class="volume-container">
	<button
		type="button"
		class="player-btn volume-btn"
		onclick={onMuteToggle}
		aria-label={muted ? $_('player.unmute', { default: 'Unmute' }) : $_('player.mute', { default: 'Mute' })}
		title={muted ? $_('player.unmute', { default: 'Unmute' }) : $_('player.mute', { default: 'Mute' })}
	>
		<PlayerIcon name={iconName} size={20} />
	</button>

	<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="volume-slider-wrap"
		bind:this={sliderEl}
		onpointerdown={handlePointerDown}
		onpointermove={handlePointerMove}
		onpointerup={handlePointerUp}
		onpointercancel={handlePointerUp}
		onkeydown={handleKeyDown}
		aria-label={$_('player.volume', { default: 'Volume' })}
		tabindex="0"
	>
		<div class="volume-track">
			<div class="volume-fill" style:width="{displayPercent}%"></div>
			<div class="volume-thumb" style:left="{displayPercent}%"></div>
		</div>
	</div>
</div>

<style>
	.volume-container {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		height: 2.25rem;
	}

	.player-btn {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.85);
		padding: 0.35rem;
		border-radius: 50%;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background 0.15s ease, color 0.15s ease, transform 0.1s ease;
	}

	.player-btn:hover {
		background: rgba(255, 255, 255, 0.15);
		color: #ffffff;
	}

	.player-btn:active {
		transform: scale(0.92);
	}

	.volume-slider-wrap {
		width: 4.5rem;
		height: 1.5rem;
		display: flex;
		align-items: center;
		cursor: pointer;
		padding: 0 0.25rem;
		outline: none;
		touch-action: none;
	}

	.volume-slider-wrap:focus-visible .volume-track {
		box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.5);
	}

	.volume-track {
		position: relative;
		width: 100%;
		height: 0.25rem;
		background: rgba(255, 255, 255, 0.25);
		border-radius: 0.15rem;
	}

	.volume-fill {
		position: absolute;
		top: 0;
		left: 0;
		height: 100%;
		background: #38bdf8;
		border-radius: 0.15rem;
	}

	.volume-thumb {
		position: absolute;
		top: 50%;
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 50%;
		background: #38bdf8;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
		transform: translate(-50%, -50%);
		transition: transform 0.1s ease;
	}

	.volume-slider-wrap:hover .volume-thumb,
	.volume-slider-wrap:focus-visible .volume-thumb {
		transform: translate(-50%, -50%) scale(1.2);
	}
</style>
