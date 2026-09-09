<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { createMpegtsPlayer } from '$lib/mpegts-player';
	import type { MultiViewSlot } from '$lib/stores/multiview';
	import PlayerIcon from '../icons/PlayerIcon.svelte';
	import LoadingQuipOverlay from '../LoadingQuipOverlay.svelte';

	interface Props {
		slot: MultiViewSlot;
		index: number;
		isAudioActive: boolean;
		isHero?: boolean;
		canMakeHero?: boolean;
		isExpanded?: boolean;
		volume?: number;
		onSelectAudio: () => void;
		onMakeHero: () => void;
		onChangeChannel: () => void;
		onToggleFullscreen: () => void;
		onClose: () => void;
	}

	let {
		slot,
		index,
		isAudioActive,
		isHero = false,
		canMakeHero = false,
		isExpanded = false,
		volume = 1.0,
		onSelectAudio,
		onMakeHero,
		onChangeChannel,
		onToggleFullscreen,
		onClose,
	}: Props = $props();

	let videoElement = $state<HTMLVideoElement | null>(null);
	let isVideoLoading = $state(true);
	let errorMessage = $state<string | null>(null);
	let errorDetail = $state<string | null>(null);
	let isHovered = $state(false);
	let destroyed = false;

	const channelNumber = $derived(slot.channel.channel_number);
	const channelName = $derived(slot.channel.name);
	const programTitle = $derived(slot.airing?.title ?? slot.channel.name);
	const isHd = $derived(slot.channel.is_hd || slot.airing?.is_hd);

	const mpegtsPlayer = createMpegtsPlayer({
		getDestroyed: () => destroyed,
		setErrorMessage: (msg) => {
			errorMessage = msg;
		},
		setErrorDetail: (det) => {
			errorDetail = det;
		},
		genericHint: () => 'Playback failed for this channel.',
	});

	function attachTilePlayer(node: HTMLVideoElement) {
		videoElement = node;
		node.volume = volume;
		node.muted = !isAudioActive;
		isVideoLoading = true;

		const handleLoadStart = () => { isVideoLoading = true; };
		const handleWaiting = () => { isVideoLoading = true; };
		const handlePlaying = () => { isVideoLoading = false; };
		const handleCanPlay = () => { isVideoLoading = false; };
		const handleLoadedData = () => { isVideoLoading = false; };

		node.addEventListener('loadstart', handleLoadStart);
		node.addEventListener('waiting', handleWaiting);
		node.addEventListener('playing', handlePlaying);
		node.addEventListener('canplay', handleCanPlay);
		node.addEventListener('loadeddata', handleLoadedData);

		if (slot.streamUrl) {
			mpegtsPlayer.createPlayerAt(node, slot.streamUrl);
		}

		return {
			destroy() {
				destroyed = true;
				node.removeEventListener('loadstart', handleLoadStart);
				node.removeEventListener('waiting', handleWaiting);
				node.removeEventListener('playing', handlePlaying);
				node.removeEventListener('canplay', handleCanPlay);
				node.removeEventListener('loadeddata', handleLoadedData);
				mpegtsPlayer.teardownPlayer();
				videoElement = null;
			},
		};
	}

	// Update audio mute state when active audio changes
	$effect(() => {
		if (videoElement) {
			videoElement.muted = !isAudioActive;
			videoElement.volume = volume;
		}
	});

	// Reconnect player when slot streamUrl changes
	let loadedStreamUrl: string | undefined;
	$effect(() => {
		const targetUrl = slot.streamUrl;
		if (loadedStreamUrl === undefined) {
			loadedStreamUrl = targetUrl;
			return;
		}
		if (targetUrl !== loadedStreamUrl) {
			loadedStreamUrl = targetUrl;
			if (videoElement && !destroyed) {
				isVideoLoading = true;
				mpegtsPlayer.teardownPlayer();
				mpegtsPlayer.createPlayerAt(videoElement, targetUrl);
			}
		}
	});
</script>

<div
	class="slot-tile"
	class:audio-active={isAudioActive}
	class:hero-tile={isHero}
	class:expanded={isExpanded}
	onmouseenter={() => (isHovered = true)}
	onmouseleave={() => (isHovered = false)}
	role="group"
	aria-label={`Feed ${index + 1}: ${channelNumber} ${channelName}`}
>
	<!-- Video Surface -->
	<div class="video-container" onclick={onSelectAudio} role="presentation">
		<!-- svelte-ignore a11y_media_has_caption -->
		<video
			autoplay
			playsinline
			controls={false}
			class="tile-video"
			use:attachTilePlayer
			crossorigin="use-credentials"
		></video>

		<!-- Loading spinner -->
		<LoadingQuipOverlay visible={(isVideoLoading || slot.loading) && !errorMessage && !slot.error} />

		<!-- Error overlay -->
		{#if slot.error || errorMessage}
			<div class="tile-error-overlay">
				<div class="error-header">
					<span class="error-icon">⚠️</span>
					<span class="error-title">{slot.error ? 'Tuner Unavailable' : 'Playback Error'}</span>
				</div>
				<p class="error-text">{slot.error || errorMessage}</p>
				{#if errorDetail && !slot.error}
					<p class="error-detail">{errorDetail}</p>
				{/if}
				<div class="error-actions">
					<button
						type="button"
						class="error-action-btn"
						onclick={(e) => {
							e.stopPropagation();
							onChangeChannel();
						}}
					>
						Change Channel
					</button>
					<button
						type="button"
						class="error-action-btn close"
						onclick={(e) => {
							e.stopPropagation();
							onClose();
						}}
					>
						Close Slot
					</button>
				</div>
			</div>
		{/if}
	</div>

	<!-- Top Overlay Badge Bar -->
	<div class="tile-top-bar" class:visible={isHovered || isAudioActive}>
		<div class="left-badges">
			<span class="channel-badge">{channelNumber}</span>
			<span class="channel-name" title={channelName}>{channelName}</span>
			{#if isHd}
				<span class="hd-badge">HD</span>
			{/if}
		</div>

		<div class="right-badges">
			{#if slot.warningMessage}
				<span class="warning-badge" title={slot.warningMessage}>⚠️ Tuner Busy</span>
			{/if}

			<button
				type="button"
				class="audio-indicator-btn"
				class:active={isAudioActive}
				onclick={(e) => {
					e.stopPropagation();
					onSelectAudio();
				}}
				aria-label={isAudioActive ? 'Audio active' : 'Click to listen'}
				title={isAudioActive ? 'Audio active' : 'Click to listen'}
			>
				<PlayerIcon name={isAudioActive ? 'volume-high' : 'volume-muted'} size={16} />
				<span class="audio-label">{isAudioActive ? 'Audio' : 'Muted'}</span>
			</button>
		</div>
	</div>

	<!-- Bottom Hover Action Bar -->
	<div class="tile-bottom-bar" class:visible={isHovered}>
		<div class="program-info">
			<span class="program-title" title={programTitle}>{programTitle}</span>
		</div>

		<div class="action-buttons">
			{#if canMakeHero}
				<button
					type="button"
					class="tile-action-btn"
					onclick={(e) => {
						e.stopPropagation();
						onMakeHero();
					}}
					aria-label={$_('multiview.make_hero', { default: 'Make Primary (Hero)' })}
					title={$_('multiview.make_hero', { default: 'Make Primary (Hero)' })}
				>
					<PlayerIcon name="star" size={16} />
				</button>
			{/if}

			<button
				type="button"
				class="tile-action-btn"
				onclick={(e) => {
					e.stopPropagation();
					onChangeChannel();
				}}
				aria-label={$_('player.channels', { default: 'Change Channel' })}
				title={$_('player.channels', { default: 'Change Channel' })}
			>
				<PlayerIcon name="channels" size={16} />
			</button>

			<button
				type="button"
				class="tile-action-btn"
				onclick={(e) => {
					e.stopPropagation();
					onToggleFullscreen();
				}}
				aria-label={isExpanded ? 'Collapse' : 'Expand Fullscreen'}
				title={isExpanded ? 'Collapse' : 'Expand Fullscreen'}
			>
				<PlayerIcon name={isExpanded ? 'fullscreen-exit' : 'fullscreen'} size={16} />
			</button>

			<button
				type="button"
				class="tile-action-btn close-btn"
				onclick={(e) => {
					e.stopPropagation();
					onClose();
				}}
				aria-label={$_('multiview.close_slot', { default: 'Close Feed' })}
				title={$_('multiview.close_slot', { default: 'Close Feed' })}
			>
				<PlayerIcon name="close" size={16} />
			</button>
		</div>
	</div>
</div>

<style>
	.slot-tile {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 180px;
		background: #000;
		border-radius: 0.85rem;
		overflow: hidden;
		box-sizing: border-box;
		border: 2px solid rgba(255, 255, 255, 0.15);
		transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.15s ease;
		display: flex;
		flex-direction: column;
	}

	.slot-tile.audio-active {
		border-color: #38bdf8;
		box-shadow: 0 0 16px rgba(56, 189, 248, 0.35);
	}

	.slot-tile:focus-visible {
		outline: 3px solid #38bdf8;
		outline-offset: 2px;
	}

	.video-container {
		position: relative;
		width: 100%;
		height: 100%;
		flex: 1;
		background: #000;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}

	.tile-video {
		width: 100%;
		height: 100%;
		object-fit: contain;
		background: #000;
	}

	.tile-error-overlay {
		position: absolute;
		inset: 0;
		background: rgba(15, 15, 20, 0.92);
		backdrop-filter: blur(8px);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 1.25rem;
		text-align: center;
		color: #f87171;
		z-index: 15;
		gap: 0.6rem;
	}

	.error-header {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.error-icon {
		font-size: 1.25rem;
	}

	.error-title {
		font-weight: 700;
		font-size: 1.05rem;
		color: #facc15;
	}

	.error-text {
		font-weight: 500;
		font-size: 0.85rem;
		line-height: 1.35;
		color: rgba(255, 255, 255, 0.9);
		margin: 0;
		max-width: 90%;
	}

	.error-detail {
		font-size: 0.75rem;
		color: rgba(255, 255, 255, 0.6);
		margin: 0;
	}

	.error-actions {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin-top: 0.4rem;
	}

	.error-action-btn {
		background: rgba(56, 189, 248, 0.2);
		border: 1px solid rgba(56, 189, 248, 0.4);
		color: #38bdf8;
		padding: 0.35rem 0.75rem;
		border-radius: 0.45rem;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.error-action-btn:hover {
		background: rgba(56, 189, 248, 0.35);
		color: #ffffff;
	}

	.error-action-btn.close {
		background: rgba(239, 68, 68, 0.2);
		border-color: rgba(239, 68, 68, 0.4);
		color: #f87171;
	}

	.error-action-btn.close:hover {
		background: rgba(239, 68, 68, 0.35);
		color: #ffffff;
	}

	/* Top Bar Overlay */
	.tile-top-bar {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.6rem 0.75rem;
		background: linear-gradient(180deg, rgba(0, 0, 0, 0.8) 0%, rgba(0, 0, 0, 0) 100%);
		pointer-events: auto;
		opacity: 0.85;
		transition: opacity 0.2s ease;
		z-index: 10;
	}

	.tile-top-bar.visible {
		opacity: 1;
	}

	.left-badges {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		min-width: 0;
	}

	.channel-badge {
		background: rgba(56, 189, 248, 0.3);
		color: #38bdf8;
		border: 1px solid rgba(56, 189, 248, 0.5);
		font-weight: 700;
		font-size: 0.75rem;
		padding: 0.1rem 0.35rem;
		border-radius: 0.25rem;
	}

	.channel-name {
		color: #ffffff;
		font-weight: 600;
		font-size: 0.85rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 140px;
	}

	.hd-badge {
		background: rgba(255, 255, 255, 0.15);
		color: #ffffff;
		font-size: 0.65rem;
		font-weight: 700;
		padding: 0.1rem 0.3rem;
		border-radius: 0.2rem;
	}

	.right-badges {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-shrink: 0;
	}

	.warning-badge {
		background: rgba(234, 179, 8, 0.25);
		color: #facc15;
		border: 1px solid rgba(234, 179, 8, 0.5);
		font-size: 0.7rem;
		font-weight: 600;
		padding: 0.1rem 0.4rem;
		border-radius: 0.25rem;
	}

	.audio-indicator-btn {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		background: rgba(0, 0, 0, 0.6);
		border: 1px solid rgba(255, 255, 255, 0.2);
		color: rgba(255, 255, 255, 0.7);
		border-radius: 1rem;
		padding: 0.2rem 0.5rem;
		font-size: 0.75rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
	}

	.audio-indicator-btn.active {
		background: #38bdf8;
		color: #000000;
		border-color: #38bdf8;
	}

	.audio-indicator-btn:hover:not(.active) {
		background: rgba(255, 255, 255, 0.2);
		color: #ffffff;
	}

	/* Bottom Bar Overlay */
	.tile-bottom-bar {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.6rem 0.75rem;
		background: linear-gradient(0deg, rgba(0, 0, 0, 0.85) 0%, rgba(0, 0, 0, 0) 100%);
		opacity: 0;
		pointer-events: none;
		transition: opacity 0.2s ease;
		z-index: 10;
	}

	.tile-bottom-bar.visible {
		opacity: 1;
		pointer-events: auto;
	}

	.program-info {
		min-width: 0;
		flex: 1;
	}

	.program-title {
		color: rgba(255, 255, 255, 0.9);
		font-size: 0.8rem;
		font-weight: 500;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		display: block;
	}

	.action-buttons {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		flex-shrink: 0;
	}

	.tile-action-btn {
		background: rgba(0, 0, 0, 0.65);
		border: 1px solid rgba(255, 255, 255, 0.2);
		color: rgba(255, 255, 255, 0.85);
		width: 1.85rem;
		height: 1.85rem;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		transition: background 0.15s ease, color 0.15s ease, transform 0.1s ease;
	}

	.tile-action-btn:hover {
		background: rgba(255, 255, 255, 0.25);
		color: #ffffff;
		transform: scale(1.1);
	}

	.tile-action-btn.close-btn:hover {
		background: rgba(239, 68, 68, 0.8);
		border-color: #ef4444;
		color: #ffffff;
	}
</style>
