<script lang="ts">
	import { _ } from 'svelte-i18n';
	import PlayerIcon from './icons/PlayerIcon.svelte';
	import CastButton from './CastButton.svelte';
	import HDHomeRunPlayerRecordMenu from './HDHomeRunPlayerRecordMenu.svelte';
	import type {
		HDHomeRunChannel,
		HDHomeRunGuideEntry,
		HDHomeRunRecordingRule,
		RecordingRuleOptions,
	} from '$lib/api';

	interface Props {
		title: string;
		subtitle?: string | null;
		channelNumber?: string;
		channelName?: string;
		canRecord?: boolean;
		currentRule?: HDHomeRunRecordingRule | null;
		isPending?: boolean;
		isActionLoading?: boolean;
		channels?: HDHomeRunChannel[];
		effectiveAiring?: HDHomeRunGuideEntry | null;
		officialDvrActive?: boolean;
		airplayAvailable?: boolean;
		syncPlayActive?: boolean;
		syncPlayParticipantsCount?: number;
		showRecordMenu?: boolean;
		showOptionsDialog?: boolean;
		showAirPlayPicker: () => void | Promise<void>;
		buildCastContentUrl: () => Promise<{ url: string; sessionId: string }>;
		onCastingChange?: (casting: boolean) => void;
		onToggleSyncPlay?: () => void;
		onRecordEpisode?: (options?: RecordingRuleOptions) => Promise<void> | void;
		onRecordSeries?: (options?: RecordingRuleOptions) => Promise<void> | void;
		onCancelRecording?: () => Promise<void> | void;
		onConfirmOptions?: (mode: 'episode' | 'series', options: RecordingRuleOptions) => void;
		onPopout?: () => void;
		onClose: () => void;
	}

	let {
		title,
		subtitle = null,
		channelNumber,
		channelName = '',
		canRecord = false,
		currentRule = null,
		isPending = false,
		isActionLoading = false,
		channels = [],
		effectiveAiring = null,
		officialDvrActive = false,
		airplayAvailable = false,
		syncPlayActive = false,
		syncPlayParticipantsCount = 0,
		showRecordMenu = $bindable(false),
		showOptionsDialog = $bindable(false),
		showAirPlayPicker,
		buildCastContentUrl,
		onCastingChange,
		onToggleSyncPlay,
		onRecordEpisode = () => {},
		onRecordSeries = () => {},
		onCancelRecording = () => {},
		onConfirmOptions = () => {},
		onPopout,
		onClose,
	}: Props = $props();
</script>

<div class="player-header">
	<div class="left-section">
		<button
			type="button"
			class="header-btn back-btn"
			onclick={onClose}
			aria-label={$_('player.close', { default: 'Close player' })}
			title={$_('player.close', { default: 'Close player' })}
		>
			<PlayerIcon name="back" size={24} />
		</button>

		<div class="title-group">
			<div class="main-title" title={title}>{title}</div>
			{#if subtitle || channelNumber}
				<div class="sub-title">
					{#if channelNumber}
						<span class="channel-badge">{channelNumber}</span>
					{/if}
					{#if subtitle}
						<span>{subtitle}</span>
					{/if}
				</div>
			{/if}
		</div>
	</div>

	<div class="right-section">

		{#if onToggleSyncPlay}
			<button
				type="button"
				class="header-btn syncplay-btn"
				class:active={syncPlayActive}
				onclick={(e) => {
					e.stopPropagation();
					onToggleSyncPlay();
				}}
				aria-label={$_('syncplay.title', { default: 'SyncPlay Watch Party' })}
				title={$_('syncplay.title', { default: 'SyncPlay Watch Party' })}
			>
				<PlayerIcon name="syncplay" size={22} />
				{#if syncPlayActive && syncPlayParticipantsCount > 0}
					<span class="syncplay-badge">{syncPlayParticipantsCount}</span>
				{/if}
			</button>
		{/if}

		{#if airplayAvailable}
			<button
				type="button"
				class="header-btn airplay-btn"
				onclick={showAirPlayPicker}
				aria-label={$_('player.airplay', { default: 'AirPlay' })}
				title={$_('player.airplay', { default: 'AirPlay' })}
			>
				<PlayerIcon name="airplay" size={22} />
			</button>
		{/if}

		{#if channelNumber || title}
			<CastButton
				title={title}
				subtitle={subtitle ?? undefined}
				buildContentUrl={buildCastContentUrl}
				onCastingChange={(casting) => onCastingChange?.(casting)}
			/>
		{/if}

		{#if onPopout}
			<button
				type="button"
				class="header-btn popout-btn"
				onclick={(e) => {
					e.stopPropagation();
					onPopout();
				}}
				aria-label={$_('player.popout', { default: 'Popout player' })}
				title={$_('player.popout', { default: 'Popout player' })}
			>
				<PlayerIcon name="popout" size={22} />
			</button>
		{/if}

		{#if canRecord}
			<HDHomeRunPlayerRecordMenu
				{currentRule}
				{isPending}
				{isActionLoading}
				{channelName}
				{channelNumber}
				{channels}
				{effectiveAiring}
				{officialDvrActive}
				bind:showRecordMenu
				bind:showOptionsDialog
				{onRecordEpisode}
				{onRecordSeries}
				{onCancelRecording}
				{onConfirmOptions}
			/>
		{/if}
	</div>
</div>

<style>
	.player-header {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		z-index: 120;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1.25rem;
		background: linear-gradient(180deg, rgba(0, 0, 0, 0.85) 0%, rgba(0, 0, 0, 0.45) 70%, rgba(0, 0, 0, 0) 100%);
		pointer-events: auto;
		transition: opacity 0.3s ease;
	}

	.left-section {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		min-width: 0;
		flex: 1;
	}

	.right-section {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-shrink: 0;
	}

	.header-btn {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.9);
		padding: 0.5rem;
		border-radius: 50%;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
		transition: background 0.15s ease, color 0.15s ease, transform 0.1s ease;
	}

	.header-btn:hover {
		background: rgba(255, 255, 255, 0.15);
		color: #ffffff;
	}

	.header-btn:active {
		transform: scale(0.92);
	}

	.back-btn {
		margin-right: 0.25rem;
	}

	.title-group {
		display: flex;
		flex-direction: column;
		min-width: 0;
		overflow: hidden;
	}

	.main-title {
		color: #ffffff;
		font-size: 1.15rem;
		font-weight: 600;
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.sub-title {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		color: rgba(255, 255, 255, 0.75);
		font-size: 0.85rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.channel-badge {
		background: rgba(56, 189, 248, 0.25);
		color: #38bdf8;
		border: 1px solid rgba(56, 189, 248, 0.4);
		padding: 0.05rem 0.35rem;
		border-radius: 0.25rem;
		font-size: 0.75rem;
		font-weight: 600;
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
		font-size: 0.65rem;
		font-weight: 700;
		width: 1rem;
		height: 1rem;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		border: 1px solid rgba(0, 0, 0, 0.8);
	}
</style>
