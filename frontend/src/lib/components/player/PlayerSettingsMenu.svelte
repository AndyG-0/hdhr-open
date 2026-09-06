<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { HDHomeRunRecordingAudioInfo } from '$lib/api';
	import PlayerIcon from './icons/PlayerIcon.svelte';
	import { keepPlayingOnNavigate, setKeepPlayingOnNavigate } from '$lib/stores/playback';

	interface Props {
		showMenu: boolean;
		playbackRate: number;
		aspectRatio: 'contain' | 'cover' | 'fill' | '16:9' | '4:3';
		seekable?: boolean;
		audioTracks?: HDHomeRunRecordingAudioInfo[];
		currentAudioIndex?: number | null;
		hasCaptions?: boolean;
		currentCaptionTrack?: 1 | 2;
		secondaryCaptions?: 'unknown' | 'available' | 'unavailable' | null;
		captionsEnabled?: boolean;
		onPlaybackRateChange: (rate: number) => void;
		onAspectRatioChange: (ratio: 'contain' | 'cover' | 'fill' | '16:9' | '4:3') => void;
		onSelectAudioTrack: (index: number) => void;
		onSelectCaptionTrack: (track: 1 | 2) => void;
		onToggleCaptions: () => void;
		onTogglePlaybackInfo: () => void;
		onClose: () => void;
	}

	let {
		showMenu = $bindable(false),
		playbackRate = 1.0,
		aspectRatio = 'contain',
		seekable = false,
		audioTracks = [],
		currentAudioIndex = null,
		hasCaptions = false,
		currentCaptionTrack = 1,
		secondaryCaptions = null,
		captionsEnabled = false,
		onPlaybackRateChange,
		onAspectRatioChange,
		onSelectAudioTrack,
		onSelectCaptionTrack,
		onToggleCaptions,
		onTogglePlaybackInfo,
		onClose,
	}: Props = $props();

	type SubmenuType = 'main' | 'speed' | 'aspect' | 'audio' | 'captions';
	let currentSubmenu = $state<SubmenuType>('main');

	const speedOptions = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];
	const aspectOptions: { label: string; value: 'contain' | 'cover' | 'fill' | '16:9' | '4:3' }[] = [
		{ label: 'Auto (Fit)', value: 'contain' },
		{ label: 'Fill / Cover', value: 'cover' },
		{ label: 'Stretch', value: 'fill' },
		{ label: '16:9', value: '16:9' },
		{ label: '4:3', value: '4:3' },
	];

	function handleSpeedSelect(speed: number) {
		onPlaybackRateChange(speed);
		currentSubmenu = 'main';
	}

	function handleAspectSelect(ratio: 'contain' | 'cover' | 'fill' | '16:9' | '4:3') {
		onAspectRatioChange(ratio);
		currentSubmenu = 'main';
	}
</script>

{#if showMenu}
	<div class="settings-popover" role="dialog" aria-label={$_('player.settings', { default: 'Playback Settings' })}>
		<div class="menu-header">
			{#if currentSubmenu !== 'main'}
				<button type="button" class="back-btn" onclick={() => (currentSubmenu = 'main')}>
					<PlayerIcon name="back" size={16} />
				</button>
			{/if}
			<span class="header-title">
				{#if currentSubmenu === 'main'}
					{$_('player.settings', { default: 'Playback Settings' })}
				{:else if currentSubmenu === 'speed'}
					{$_('player.playback_speed', { default: 'Playback Speed' })}
				{:else if currentSubmenu === 'aspect'}
					{$_('player.aspect_ratio', { default: 'Aspect Ratio' })}
				{:else if currentSubmenu === 'audio'}
					{$_('player.audio_tracks', { default: 'Audio Tracks' })}
				{:else if currentSubmenu === 'captions'}
					{$_('player.caption_tracks', { default: 'Closed Captions' })}
				{/if}
			</span>
			<button type="button" class="close-btn" onclick={onClose}>✕</button>
		</div>

		<div class="menu-items">
			{#if currentSubmenu === 'main'}
				{#if seekable}
					<button type="button" class="menu-item nav" onclick={() => (currentSubmenu = 'speed')}>
						<span>{$_('player.playback_speed', { default: 'Speed' })}</span>
						<span class="item-value">{playbackRate}x ›</span>
					</button>
				{/if}

				<button type="button" class="menu-item nav" onclick={() => (currentSubmenu = 'aspect')}>
					<span>{$_('player.aspect_ratio', { default: 'Aspect Ratio' })}</span>
					<span class="item-value uppercase">{aspectRatio} ›</span>
				</button>

				{#if audioTracks.length > 1}
					<button type="button" class="menu-item nav" onclick={() => (currentSubmenu = 'audio')}>
						<span>{$_('player.audio_tracks', { default: 'Audio' })}</span>
						<span class="item-value">
							{audioTracks.find((t) => t.index === (currentAudioIndex ?? 0))?.title ??
								audioTracks.find((t) => t.index === (currentAudioIndex ?? 0))?.language?.toUpperCase() ??
								`Track ${(currentAudioIndex ?? 0) + 1}`} ›
						</span>
					</button>
				{/if}

				{#if seekable && hasCaptions}
					<button type="button" class="menu-item nav" onclick={() => (currentSubmenu = 'captions')}>
						<span>{$_('player.caption_tracks', { default: 'Captions' })}</span>
						<span class="item-value">
							{captionsEnabled ? `Track ${currentCaptionTrack}` : $_('common.off', { default: 'Off' })} ›
						</span>
					</button>
				{/if}

				<button
					type="button"
					class="menu-item"
					onclick={() => {
						onTogglePlaybackInfo();
						showMenu = false;
					}}
				>
					<span class="icon-label">
						<PlayerIcon name="info" size={16} />
						{$_('player.playback_info', { default: 'Playback Info / Stats' })}
					</span>
				</button>

				<button
					type="button"
					class="menu-item"
					class:selected={$keepPlayingOnNavigate}
					onclick={() => setKeepPlayingOnNavigate(!$keepPlayingOnNavigate)}
				>
					<span>{$_('player.keep_playing_label', { default: 'Keep playing when I navigate away' })}</span>
					{#if $keepPlayingOnNavigate}<span>✓</span>{/if}
				</button>
			{:else if currentSubmenu === 'speed'}
				{#each speedOptions as speed (speed)}
					<button
						type="button"
						class="menu-item"
						class:selected={playbackRate === speed}
						onclick={() => handleSpeedSelect(speed)}
					>
						<span>{speed === 1 ? '1.0x (Normal)' : `${speed}x`}</span>
						{#if playbackRate === speed}<span>✓</span>{/if}
					</button>
				{/each}
			{:else if currentSubmenu === 'aspect'}
				{#each aspectOptions as opt (opt.value)}
					<button
						type="button"
						class="menu-item"
						class:selected={aspectRatio === opt.value}
						onclick={() => handleAspectSelect(opt.value)}
					>
						<span>{opt.label}</span>
						{#if aspectRatio === opt.value}<span>✓</span>{/if}
					</button>
				{/each}
			{:else if currentSubmenu === 'audio'}
				{#each audioTracks as track (track.index)}
					<button
						type="button"
						class="menu-item"
						class:selected={(currentAudioIndex ?? 0) === track.index}
						onclick={() => {
							onSelectAudioTrack(track.index);
							currentSubmenu = 'main';
						}}
					>
						<span>
							{track.title || (track.language ? track.language.toUpperCase() : `Track ${track.index + 1}`)}
							{#if track.channels}({track.channels}ch){/if}
						</span>
						{#if (currentAudioIndex ?? 0) === track.index}
							<span>✓</span>
						{/if}
					</button>
				{/each}
			{:else if currentSubmenu === 'captions'}
				<button
					type="button"
					class="menu-item"
					class:selected={!captionsEnabled}
					onclick={() => {
						if (captionsEnabled) onToggleCaptions();
						currentSubmenu = 'main';
					}}
				>
					<span>{$_('common.off', { default: 'Off' })}</span>
					{#if !captionsEnabled}<span>✓</span>{/if}
				</button>

				<button
					type="button"
					class="menu-item"
					class:selected={captionsEnabled && currentCaptionTrack === 1}
					onclick={() => {
						if (!captionsEnabled) onToggleCaptions();
						onSelectCaptionTrack(1);
						currentSubmenu = 'main';
					}}
				>
					<span>{$_('player.caption_track_1', { default: 'Track 1 (CC1)' })}</span>
					{#if captionsEnabled && currentCaptionTrack === 1}<span>✓</span>{/if}
				</button>

				{#if secondaryCaptions !== null}
					<button
						type="button"
						class="menu-item"
						class:selected={captionsEnabled && currentCaptionTrack === 2}
						disabled={secondaryCaptions === 'unavailable'}
						onclick={() => {
							if (!captionsEnabled) onToggleCaptions();
							onSelectCaptionTrack(2);
							currentSubmenu = 'main';
						}}
					>
						<span>
							{$_('player.caption_track_2', { default: 'Track 2 (CC2)' })}
							{#if secondaryCaptions === 'unavailable'}
								({$_('player.caption_track_unavailable', { default: 'unavailable' })})
							{/if}
						</span>
						{#if captionsEnabled && currentCaptionTrack === 2}<span>✓</span>{/if}
					</button>
				{/if}
			{/if}
		</div>
	</div>
{/if}

<style>
	.settings-popover {
		position: absolute;
		bottom: 100%;
		right: 0;
		margin-bottom: 0.75rem;
		width: 15rem;
		max-height: 20rem;
		background: rgba(22, 22, 26, 0.96);
		border: 1px solid rgba(255, 255, 255, 0.18);
		border-radius: 0.75rem;
		box-shadow: 0 12px 36px rgba(0, 0, 0, 0.75);
		backdrop-filter: blur(16px);
		z-index: 150;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		animation: popover-fade 0.15s ease;
	}

	@keyframes popover-fade {
		from {
			opacity: 0;
			transform: translateY(6px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.menu-header {
		display: flex;
		align-items: center;
		padding: 0.6rem 0.75rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		gap: 0.5rem;
	}

	.back-btn,
	.close-btn {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.7);
		cursor: pointer;
		padding: 0.2rem;
		border-radius: 0.25rem;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.back-btn:hover,
	.close-btn:hover {
		color: #ffffff;
		background: rgba(255, 255, 255, 0.15);
	}

	.header-title {
		flex: 1;
		font-size: 0.85rem;
		font-weight: 600;
		color: #ffffff;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.menu-items {
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		padding: 0.35rem 0;
	}

	.menu-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.55rem 0.85rem;
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.88);
		font-size: 0.85rem;
		cursor: pointer;
		text-align: left;
		transition: background 0.12s ease, color 0.12s ease;
	}

	.menu-item:hover {
		background: rgba(255, 255, 255, 0.12);
		color: #ffffff;
	}

	.menu-item.selected {
		color: #38bdf8;
		font-weight: 600;
		background: rgba(56, 189, 248, 0.15);
	}

	.menu-item:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.item-value {
		font-size: 0.8rem;
		color: rgba(255, 255, 255, 0.55);
	}

	.uppercase {
		text-transform: uppercase;
	}

	.icon-label {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
</style>
