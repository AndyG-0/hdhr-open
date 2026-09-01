<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { HDHomeRunGuideEntry, HDHomeRunRecordingRule, RecordingRuleOptions, HDHomeRunChannel } from '$lib/api';
	import HDHomeRunRecordingOptionsDialog from '../details/HDHomeRunRecordingOptionsDialog.svelte';

	interface Props {
		currentRule: HDHomeRunRecordingRule | null;
		isPending: boolean;
		isActionLoading: boolean;
		channelName: string;
		channels?: HDHomeRunChannel[];
		effectiveAiring: HDHomeRunGuideEntry | null;
		officialDvrActive: boolean;
		showRecordMenu: boolean;
		showOptionsDialog: boolean;
		onRecordEpisode: (options?: RecordingRuleOptions) => Promise<void> | void;
		onRecordSeries: (options?: RecordingRuleOptions) => Promise<void> | void;
		onCancelRecording: () => Promise<void> | void;
		onConfirmOptions: (mode: 'episode' | 'series', options: RecordingRuleOptions) => void;
	}

	let {
		currentRule,
		isPending,
		isActionLoading,
		channelName,
		channels = [],
		effectiveAiring,
		officialDvrActive,
		showRecordMenu = $bindable(),
		showOptionsDialog = $bindable(),
		onRecordEpisode,
		onRecordSeries,
		onCancelRecording,
		onConfirmOptions,
	}: Props = $props();
</script>

<div class="menu-popover-wrap">
	<button
		class="control-btn record-btn"
		class:active={showRecordMenu}
		class:recording={currentRule !== null}
		onclick={() => (showRecordMenu = !showRecordMenu)}
		disabled={isActionLoading}
		aria-label={currentRule ? $_('player.recording_active') : $_('player.record')}
		title={currentRule ? $_('player.recording_active') : $_('player.record')}
	>
		<span class="record-dot" class:pulsing={isPending}></span>
		{#if currentRule}
			{$_('player.recording_active')}
		{:else}
			{$_('player.record')}
		{/if}
	</button>
	{#if showRecordMenu}
		<div class="popover-menu record-popover">
			<div class="menu-header">
				{effectiveAiring?.title ?? channelName}
			</div>
			<div class="menu-items">
				{#if currentRule}
					{#if isPending}
						<div class="pending-hint">{$_('player.pending_confirmation')}</div>
					{/if}
					<button class="menu-item danger" disabled={isActionLoading} onclick={onCancelRecording}>
						{$_('player.cancel_recording')}
					</button>
				{:else}
					<button class="menu-item" disabled={isActionLoading} onclick={() => onRecordEpisode()}>
						🔴 {$_('player.record_episode')}
					</button>
					{#if effectiveAiring?.series_id || effectiveAiring?.title}
						<button class="menu-item" disabled={isActionLoading} onclick={() => onRecordSeries()}>
							{$_('player.record_series')}
						</button>
					{/if}
					<button
						class="menu-item"
						disabled={isActionLoading}
						onclick={() => {
							showRecordMenu = false;
							showOptionsDialog = true;
						}}
					>
						⚙️ {$_('player.recording_options')}
					</button>
				{/if}
			</div>
		</div>
	{/if}
</div>

{#if showOptionsDialog && effectiveAiring}
	<HDHomeRunRecordingOptionsDialog
		airing={effectiveAiring}
		{channelName}
		channelNumber={effectiveAiring.channel_number}
		{channels}
		canRecordSeries={Boolean(effectiveAiring.series_id || effectiveAiring.title)}
		{officialDvrActive}
		existingRule={currentRule}
		loading={isActionLoading}
		onCancelRule={async () => {
			await onCancelRecording();
			showOptionsDialog = false;
		}}
		onConfirm={onConfirmOptions}
		onClose={() => (showOptionsDialog = false)}
	/>
{/if}

<style>
	.menu-popover-wrap {
		position: relative;
	}

	.popover-menu {
		position: absolute;
		top: 100%;
		right: 0;
		margin-top: 0.5rem;
		width: 12rem;
		max-height: 16rem;
		background: rgba(20, 20, 20, 0.95);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.6rem;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(12px);
		z-index: 120;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.menu-header {
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: rgba(255, 255, 255, 0.5);
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
	}

	.menu-items {
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		padding: 0.25rem 0;
	}

	.menu-item {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.85);
		padding: 0.5rem 0.75rem;
		text-align: left;
		font-size: 0.85rem;
		cursor: pointer;
	}

	.menu-item:hover {
		background: rgba(255, 255, 255, 0.15);
		color: #fff;
	}

	.control-btn {
		background: rgba(255, 255, 255, 0.15);
		border: 1px solid rgba(255, 255, 255, 0.3);
		border-radius: 0.4rem;
		padding: 0.3rem 0.6rem;
		color: #fff;
		font-size: 0.85rem;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.control-btn:hover {
		background: rgba(255, 255, 255, 0.25);
	}

	.control-btn.active {
		background: rgba(56, 189, 248, 0.25);
		border-color: #38bdf8;
		color: #38bdf8;
	}

	.record-btn {
		position: relative;
	}

	.record-btn.recording {
		background: rgba(224, 90, 90, 0.25);
		border-color: rgba(224, 90, 90, 0.6);
		color: #ffb4b4;
	}

	.record-btn.recording:hover {
		background: rgba(224, 90, 90, 0.35);
	}

	.record-dot {
		display: inline-block;
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 50%;
		background: #ff5555;
	}

	.record-dot.pulsing {
		animation: record-pulse 1.5s infinite;
	}

	@keyframes record-pulse {
		0%,
		100% {
			opacity: 1;
			transform: scale(1);
		}
		50% {
			opacity: 0.4;
			transform: scale(0.85);
		}
	}

	.record-popover {
		width: 14rem;
	}

	.menu-item.danger {
		color: #ff8888;
	}

	.menu-item.danger:hover {
		background: rgba(224, 90, 90, 0.2);
		color: #ffb4b4;
	}

	.pending-hint {
		padding: 0.35rem 0.75rem;
		font-size: 0.75rem;
		color: #eab308;
		font-style: italic;
	}
</style>
