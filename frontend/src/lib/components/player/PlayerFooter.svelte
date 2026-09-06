<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { CommercialSegment, HDHomeRunRecordingAudioInfo } from '$lib/api';
	import PlayerIcon from './icons/PlayerIcon.svelte';
	import PlayerScrubBar from './PlayerScrubBar.svelte';
	import PlayerVolumeControl from './PlayerVolumeControl.svelte';
	import PlayerSettingsMenu from './PlayerSettingsMenu.svelte';
	import type { ThumbnailCue } from '$lib/vtt-parser';

	interface Props {
		displayedPosition: number;
		duration: number | null;
		isInProgress?: boolean;
		seekable?: boolean;
		thumbnailsAvailable?: boolean;
		thumbSpriteUrl?: string;
		thumbnailCues?: ThumbnailCue[];
		commercialSegments?: CommercialSegment[];
		paused?: boolean;
		volume?: number;
		muted?: boolean;
		isFavorited?: boolean;
		channelNumber?: string | null;
		pipSupported?: boolean;
		isPipActive?: boolean;
		isFullscreen?: boolean;
		captionsEnabled?: boolean;
		hasCaptions?: boolean;
		audioTracks?: HDHomeRunRecordingAudioInfo[];
		currentAudioIndex?: number | null;
		currentCaptionTrack?: 1 | 2;
		secondaryCaptions?: 'unknown' | 'available' | 'unavailable' | null;
		scheduledEndTime?: number | null;
		isLive?: boolean;
		playbackRate?: number;
		aspectRatio?: 'contain' | 'cover' | 'fill' | '16:9' | '4:3';
		showAudioMenu?: boolean;
		showSettingsMenu?: boolean;
		onSeek: (targetSeconds: number) => void;
		onTogglePlay: () => void;
		onRewind: (seconds?: number) => void;
		onFastForward: (seconds?: number) => void;
		onVolumeChange: (vol: number) => void;
		onMuteToggle: () => void;
		onToggleFavorite?: () => void;
		syncPlayActive?: boolean;
		syncPlayParticipantsCount?: number;
		onToggleSyncPlay?: () => void;
		onTogglePip?: () => void;
		onToggleFullscreen: () => void;
		onToggleCaptions: () => void;
		onSelectAudioTrack: (index: number) => void;
		onSelectCaptionTrack: (track: 1 | 2) => void;
		onPlaybackRateChange: (rate: number) => void;
		onAspectRatioChange: (ratio: 'contain' | 'cover' | 'fill' | '16:9' | '4:3') => void;
		onTogglePlaybackInfo: () => void;
		channelSwitcherAvailable?: boolean;
		onToggleChannelDrawer?: () => void;
	}

	let {
		displayedPosition,
		duration,
		isInProgress = false,
		seekable = false,
		thumbnailsAvailable = false,
		thumbSpriteUrl = '',
		thumbnailCues = [],
		commercialSegments = [],
		paused = false,
		volume = 1,
		muted = false,
		isFavorited = false,
		channelNumber = null,
		pipSupported = false,
		isPipActive = false,
		isFullscreen = false,
		captionsEnabled = false,
		hasCaptions = false,
		audioTracks = [],
		currentAudioIndex = null,
		currentCaptionTrack = 1,
		secondaryCaptions = null,
		scheduledEndTime = null,
		isLive = false,
		playbackRate = 1.0,
		aspectRatio = 'contain',
		showAudioMenu = $bindable(false),
		showSettingsMenu = $bindable(false),
		onSeek,
		onTogglePlay,
		onRewind,
		onFastForward,
		onVolumeChange,
		onMuteToggle,
		syncPlayActive = false,
		syncPlayParticipantsCount = 0,
		onToggleSyncPlay,
		onToggleFavorite,
		onTogglePip,
		onToggleFullscreen,
		onToggleCaptions,
		onSelectAudioTrack,
		onSelectCaptionTrack,
		onPlaybackRateChange,
		onAspectRatioChange,
		onTogglePlaybackInfo,
		channelSwitcherAvailable = false,
		onToggleChannelDrawer,
	}: Props = $props();

	let showCaptionMenu = $state(false);

	// Dynamic "Ends at hh:mm AM/PM" calculation
	const endsAtText = $derived.by<string>(() => {
		if (isLive) {
			if (scheduledEndTime && scheduledEndTime > 0) {
				const endMs = scheduledEndTime * 1000;
				const timeStr = new Date(endMs).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
				return `Ends at ${timeStr}`;
			}
			return '';
		}

		if (seekable && duration && duration > 0) {
			const remainingSec = Math.max(0, duration - displayedPosition);
			const endMs = Date.now() + remainingSec * 1000;
			const timeStr = new Date(endMs).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
			return `Ends at ${timeStr}`;
		}
		return '';
	});
</script>

<div class="player-footer">
	<!-- Tier 1: Scrub / Progress Bar -->
	{#if seekable}
		<div class="scrub-tier">
			<PlayerScrubBar
				{displayedPosition}
				{duration}
				{isInProgress}
				{seekable}
				{thumbnailsAvailable}
				{thumbSpriteUrl}
				{thumbnailCues}
				{commercialSegments}
				{onSeek}
			/>
		</div>
	{/if}

	<!-- Tier 2: Action Controls -->
	<div class="controls-tier">
		<!-- Left Cluster -->
		<div class="controls-left">
			{#if seekable}
				<button
					type="button"
					class="ctrl-btn"
					onclick={() => onRewind(10)}
					aria-label={$_('player.rewind', { default: 'Rewind 10s' })}
					title={$_('player.rewind', { default: 'Rewind 10s (Left Arrow)' })}
				>
					<PlayerIcon name="previous" size={22} />
				</button>
			{/if}

			<button
				type="button"
				class="ctrl-btn play-pause-btn"
				onclick={onTogglePlay}
				aria-label={paused ? $_('player.play', { default: 'Play' }) : $_('player.pause', { default: 'Pause' })}
				title={paused ? $_('player.play', { default: 'Play (Space)' }) : $_('player.pause', { default: 'Pause (Space)' })}
			>
				<PlayerIcon name={paused ? 'play' : 'pause'} size={26} />
			</button>

			{#if seekable}
				<button
					type="button"
					class="ctrl-btn"
					onclick={() => onFastForward(10)}
					aria-label={$_('player.fast_forward', { default: 'Fast Forward 10s' })}
					title={$_('player.fast_forward', { default: 'Fast Forward 10s (Right Arrow)' })}
				>
					<PlayerIcon name="next" size={22} />
				</button>
			{/if}

			{#if endsAtText}
				<div class="ends-at-label">
					{endsAtText}
				</div>
			{/if}
		</div>

		<!-- Right Cluster -->
		<div class="controls-right">
			{#if (isLive || channelNumber) && onToggleFavorite}
				<button
					type="button"
					class="ctrl-btn"
					class:active={isFavorited}
					onclick={onToggleFavorite}
					aria-label={isFavorited
						? $_('hdhomerun.detail.remove_favorite', { default: 'Remove from favorites' })
						: $_('hdhomerun.detail.add_favorite', { default: 'Add to favorites' })}
					title={isFavorited
						? $_('hdhomerun.detail.remove_favorite', { default: 'Remove from favorites' })
						: $_('hdhomerun.detail.add_favorite', { default: 'Add to favorites' })}
				>
					<PlayerIcon name={isFavorited ? 'heart-filled' : 'heart'} size={20} />
				</button>
			{/if}

			{#if pipSupported && onTogglePip}
				<button
					type="button"
					class="ctrl-btn"
					class:active={isPipActive}
					onclick={onTogglePip}
					aria-label={$_('player.pip', { default: 'Picture in Picture' })}
					title={$_('player.pip', { default: 'Picture in Picture (P)' })}
				>
					<PlayerIcon name="pip" size={20} />
				</button>
			{/if}

			{#if audioTracks.length > 1}
				<div class="popover-wrapper">
					<button
						type="button"
						class="ctrl-btn"
						class:active={showAudioMenu}
						onclick={() => {
							showAudioMenu = !showAudioMenu;
							showSettingsMenu = false;
						}}
						aria-label={$_('player.audio_tracks', { default: 'Audio Tracks' })}
						title={$_('player.audio_tracks', { default: 'Audio Tracks' })}
					>
						<PlayerIcon name="audio" size={20} />
					</button>

					{#if showAudioMenu}
						<div class="quick-popover" role="dialog">
							<div class="popover-header">{$_('player.audio_tracks', { default: 'Audio Tracks' })}</div>
							<div class="popover-items">
								{#each audioTracks as track (track.index)}
									<button
										type="button"
										class="popover-item"
										class:selected={(currentAudioIndex ?? 0) === track.index}
										onclick={() => {
											onSelectAudioTrack(track.index);
											showAudioMenu = false;
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
							</div>
						</div>
					{/if}
				</div>
			{/if}

			<PlayerVolumeControl
				{volume}
				{muted}
				{onVolumeChange}
				{onMuteToggle}
			/>

			<!-- Settings Gear -->
			<div class="popover-wrapper">
				<button
					type="button"
					class="ctrl-btn"
					class:active={showSettingsMenu}
					onclick={() => {
						showSettingsMenu = !showSettingsMenu;
						showAudioMenu = false;
					}}
					aria-label={$_('player.settings', { default: 'Settings' })}
					title={$_('player.settings', { default: 'Playback Settings' })}
				>
					<PlayerIcon name="settings" size={20} />
				</button>

				<PlayerSettingsMenu
					bind:showMenu={showSettingsMenu}
					{playbackRate}
					{aspectRatio}
					{seekable}
					{audioTracks}
					{currentAudioIndex}
					{hasCaptions}
					{currentCaptionTrack}
					{secondaryCaptions}
					{captionsEnabled}
					{onPlaybackRateChange}
					{onAspectRatioChange}
					{onSelectAudioTrack}
					{onSelectCaptionTrack}
					{onToggleCaptions}
					{onTogglePlaybackInfo}
					onClose={() => (showSettingsMenu = false)}
				/>
			</div>

			{#if hasCaptions}
				<button
					type="button"
					class="ctrl-btn cc-btn"
					class:active={captionsEnabled}
					onclick={onToggleCaptions}
					aria-label={$_('player.subtitles', { default: 'Subtitles / Closed Captions' })}
					title={$_('player.subtitles', { default: 'Subtitles / Closed Captions (C)' })}
				>
					<PlayerIcon name="captions" size={20} />
				</button>

				{#if secondaryCaptions !== null}
					<div class="popover-wrapper">
						<button
							type="button"
							class="ctrl-btn cc-track-btn"
							class:active={showCaptionMenu}
							onclick={() => {
								showCaptionMenu = !showCaptionMenu;
								showAudioMenu = false;
								showSettingsMenu = false;
							}}
							aria-label={$_('player.caption_tracks', { default: 'CC Track' })}
							title={$_('player.caption_tracks', { default: 'CC Track' })}
						>
							CC {currentCaptionTrack}
						</button>

						{#if showCaptionMenu}
							<div class="quick-popover" role="dialog">
								<div class="popover-header">{$_('player.caption_tracks', { default: 'CC Track' })}</div>
								<div class="popover-items">
									<button
										type="button"
										class="popover-item"
										class:selected={currentCaptionTrack === 1}
										onclick={() => {
											onSelectCaptionTrack(1);
											showCaptionMenu = false;
										}}
									>
										<span>{$_('player.caption_track_1', { default: 'Track 1' })}</span>
										{#if currentCaptionTrack === 1}<span>✓</span>{/if}
									</button>
									<button
										type="button"
										class="popover-item"
										class:selected={currentCaptionTrack === 2}
										disabled={secondaryCaptions === 'unavailable'}
										onclick={() => {
											onSelectCaptionTrack(2);
											showCaptionMenu = false;
										}}
									>
										<span>
											{$_('player.caption_track_2', { default: 'Track 2' })}
											{#if secondaryCaptions === 'unavailable'}
												({$_('player.caption_track_unavailable', { default: 'unavailable' })})
											{/if}
										</span>
										{#if currentCaptionTrack === 2}<span>✓</span>{/if}
									</button>
								</div>
							</div>
						{/if}
					</div>
				{/if}
			{/if}

			{#if channelSwitcherAvailable && onToggleChannelDrawer}
				<button
					type="button"
					class="ctrl-btn"
					onclick={(e) => {
						e.stopPropagation();
						onToggleChannelDrawer();
					}}
					aria-label={$_('player.channels', { default: 'Channels' })}
					title={$_('player.channels', { default: 'Switch Channel' })}
				>
					<PlayerIcon name="channels" size={20} />
				</button>
			{/if}

			{#if onToggleSyncPlay}
				<button
					type="button"
					class="ctrl-btn syncplay-btn"
					class:active={syncPlayActive}
					onclick={(e) => {
						e.stopPropagation();
						onToggleSyncPlay();
					}}
					aria-label={$_('syncplay.title', { default: 'SyncPlay Watch Party' })}
					title={$_('syncplay.title', { default: 'SyncPlay Watch Party' })}
				>
					<PlayerIcon name="syncplay" size={20} />
					{#if syncPlayActive && syncPlayParticipantsCount > 0}
						<span class="syncplay-badge">{syncPlayParticipantsCount}</span>
					{/if}
				</button>
			{/if}

			<button
				type="button"
				class="ctrl-btn info-btn"
				onclick={onTogglePlaybackInfo}
				aria-label={$_('player.playback_info', { default: 'Playback Info' })}
				title={$_('player.playback_info', { default: 'Playback Info' })}
			>
				<PlayerIcon name="info" size={20} />
			</button>

			<button
				type="button"
				class="ctrl-btn fullscreen-btn"
				onclick={onToggleFullscreen}
				aria-label={isFullscreen ? $_('player.exit_fullscreen', { default: 'Exit Fullscreen' }) : $_('player.fullscreen', { default: 'Fullscreen' })}
				title={isFullscreen ? $_('player.exit_fullscreen', { default: 'Exit Fullscreen (F)' }) : $_('player.fullscreen', { default: 'Fullscreen (F)' })}
			>
				<PlayerIcon name={isFullscreen ? 'fullscreen-exit' : 'fullscreen'} size={22} />
			</button>
		</div>
	</div>
</div>

<style>
	.player-footer {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		z-index: 120;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.75rem 1.25rem 1rem;
		background: linear-gradient(0deg, rgba(0, 0, 0, 0.9) 0%, rgba(0, 0, 0, 0.5) 75%, rgba(0, 0, 0, 0) 100%);
		pointer-events: auto;
		transition: opacity 0.3s ease;
	}

	.scrub-tier {
		width: 100%;
	}

	.controls-tier {
		display: flex;
		align-items: center;
		justify-content: space-between;
		width: 100%;
		gap: 1rem;
	}

	.controls-left,
	.controls-right {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.ctrl-btn {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.85);
		padding: 0.45rem;
		border-radius: 50%;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background 0.15s ease, color 0.15s ease, transform 0.1s ease;
	}

	.ctrl-btn:hover {
		background: rgba(255, 255, 255, 0.18);
		color: #ffffff;
	}

	.syncplay-btn {
		position: relative;
	}

	.syncplay-btn.active {
		color: #38bdf8;
		background: rgba(56, 189, 248, 0.2);
	}

	.syncplay-badge {
		position: absolute;
		top: -2px;
		right: -2px;
		background: #38bdf8;
		color: #000000;
		font-size: 0.62rem;
		font-weight: 700;
		min-width: 0.95rem;
		height: 0.95rem;
		border-radius: 9999px;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0 0.15rem;
		border: 1px solid rgba(0, 0, 0, 0.8);
	}

	.ctrl-btn:active {
		transform: scale(0.9);
	}

	.ctrl-btn.active {
		color: #38bdf8;
		background: rgba(56, 189, 248, 0.2);
	}

	.play-pause-btn {
		color: #ffffff;
		padding: 0.55rem;
		background: rgba(255, 255, 255, 0.1);
	}

	.play-pause-btn:hover {
		background: rgba(255, 255, 255, 0.25);
	}

	.ends-at-label {
		color: rgba(255, 255, 255, 0.75);
		font-size: 0.82rem;
		font-weight: 500;
		margin-left: 0.75rem;
		white-space: nowrap;
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}

	.popover-wrapper {
		position: relative;
	}

	.quick-popover {
		position: absolute;
		bottom: 100%;
		right: 0;
		margin-bottom: 0.75rem;
		width: 13rem;
		max-height: 16rem;
		background: rgba(22, 22, 26, 0.96);
		border: 1px solid rgba(255, 255, 255, 0.18);
		border-radius: 0.65rem;
		box-shadow: 0 12px 36px rgba(0, 0, 0, 0.75);
		backdrop-filter: blur(16px);
		z-index: 150;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		animation: popover-fade 0.15s ease;
	}

	.popover-header {
		padding: 0.6rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: rgba(255, 255, 255, 0.55);
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
	}

	.popover-items {
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		padding: 0.25rem 0;
	}

	.popover-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0.75rem;
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.85);
		font-size: 0.85rem;
		cursor: pointer;
		text-align: left;
	}

	.popover-item:hover {
		background: rgba(255, 255, 255, 0.12);
		color: #ffffff;
	}

	.popover-item.selected {
		color: #38bdf8;
		font-weight: 600;
		background: rgba(56, 189, 248, 0.15);
	}

	@keyframes popover-fade {
		from { opacity: 0; transform: translateY(6px); }
		to { opacity: 1; transform: translateY(0); }
	}
</style>
