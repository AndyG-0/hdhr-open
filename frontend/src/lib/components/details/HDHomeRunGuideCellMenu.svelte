<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { HDHomeRunGuideEntry, HDHomeRunRecordingRule } from '$lib/api';

	interface Props {
		airing: HDHomeRunGuideEntry;
		channelName: string;
		x: number;
		y: number;
		existingRule: HDHomeRunRecordingRule | null;
		loading: boolean;
		pending: boolean;
		onRecordEpisode: () => void;
		onRecordSeries: () => void;
		onOpenOptions: () => void;
		onCancelRule: (ruleId: string) => void;
		onClose: () => void;
	}

	let {
		airing,
		channelName,
		x,
		y,
		existingRule,
		loading,
		pending,
		onRecordEpisode,
		onRecordSeries,
		onOpenOptions,
		onCancelRule,
		onClose,
	}: Props = $props();

	let menuEl = $state<HTMLDivElement | null>(null);
	// svelte-ignore state_referenced_locally -- seeds the initial position
	// before the clamping effect below measures the rendered menu and
	// overwrites it.
	let style = $state(`left: ${x}px; top: ${y}px;`);

	// Clamp the popover inside the viewport once it has a measurable size —
	// the anchor point is the pointer/click position, which can sit right at
	// a screen edge.
	$effect(() => {
		if (!menuEl) return;
		const rect = menuEl.getBoundingClientRect();
		const maxLeft = window.innerWidth - rect.width - 8;
		const maxTop = window.innerHeight - rect.height - 8;
		const left = Math.min(x, Math.max(8, maxLeft));
		const top = Math.min(y, Math.max(8, maxTop));
		style = `left: ${left}px; top: ${top}px;`;
	});

	function handleWindowPointerDown(e: PointerEvent) {
		if (menuEl && e.target instanceof Node && !menuEl.contains(e.target)) onClose();
	}

	function handleWindowKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

<svelte:window onpointerdown={handleWindowPointerDown} onkeydown={handleWindowKeydown} />

<div class="menu-backdrop"></div>
<div class="cell-menu" bind:this={menuEl} {style} role="menu">
	<div class="menu-header">
		<span class="menu-title">{airing.title}</span>
		<span class="menu-channel">{channelName}</span>
	</div>
	{#if existingRule}
		{#if pending}
			<div class="menu-pending-hint">{$_('hdhomerun.detail.pending_confirmation')}</div>
		{/if}
		<button
			class="menu-item danger"
			disabled={loading}
			onclick={() => onCancelRule(existingRule.RecordingRuleID)}
			role="menuitem"
		>
			{$_('hdhomerun.detail.cancel_recording')}
		</button>
	{:else}
		<button class="menu-item" disabled={loading} onclick={onRecordEpisode} role="menuitem">
			🔴 {$_('hdhomerun.detail.record_episode')}
		</button>
		{#if airing.series_id}
			<button class="menu-item" disabled={loading} onclick={onRecordSeries} role="menuitem">
				{$_('hdhomerun.detail.record_series')}
			</button>
		{/if}
		<button class="menu-item" disabled={loading} onclick={onOpenOptions} role="menuitem">
			⚙️ {$_('hdhomerun.detail.recording_options')}
		</button>
	{/if}
</div>

<style>
	.menu-backdrop {
		position: fixed;
		inset: 0;
		z-index: 50;
	}

	.cell-menu {
		position: fixed;
		z-index: 51;
		min-width: 12rem;
		max-width: 16rem;
		display: flex;
		flex-direction: column;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		box-shadow: 0 0.5rem 1.5rem rgba(0, 0, 0, 0.25);
		padding: 0.35rem;
		gap: 0.15rem;
	}

	.menu-header {
		display: flex;
		flex-direction: column;
		padding: 0.35rem 0.5rem 0.4rem;
		border-bottom: 1px solid var(--color-border);
		margin-bottom: 0.15rem;
	}

	.menu-title {
		font-weight: 600;
		font-size: 0.85rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.menu-channel {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.menu-item {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		background: none;
		border: none;
		border-radius: 0.35rem;
		padding: 0.5rem 0.6rem;
		font-size: 0.85rem;
		color: var(--color-text);
		text-align: left;
		cursor: pointer;
	}

	.menu-item:hover:not(:disabled) {
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.08));
	}

	.menu-item:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.menu-item.danger {
		color: var(--color-error, #e05a5a);
	}

	.menu-pending-hint {
		font-size: 0.75rem;
		color: var(--color-warning, #d9a441);
		padding: 0.1rem 0.6rem 0.35rem;
	}
</style>
