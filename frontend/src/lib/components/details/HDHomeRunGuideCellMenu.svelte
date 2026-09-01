<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { HDHomeRunGuideEntry, HDHomeRunRecordingRule } from '$lib/api';

	interface Props {
		airing: HDHomeRunGuideEntry;
		channelName: string;
		channelNumber?: string;
		isHd?: boolean;
		x: number;
		y: number;
		existingRule: HDHomeRunRecordingRule | null;
		loading: boolean;
		pending: boolean;
		onWatch?: () => void;
		onRecordEpisode: () => void;
		onRecordSeries: () => void;
		onOpenOptions: () => void;
		onCancelRule: (ruleId: string) => void;
		onClose: () => void;
	}

	let {
		airing,
		channelName,
		channelNumber,
		isHd = false,
		x,
		y,
		existingRule,
		loading,
		pending,
		onWatch,
		onRecordEpisode,
		onRecordSeries,
		onOpenOptions,
		onCancelRule,
		onClose,
	}: Props = $props();

	let menuEl = $state<HTMLDivElement | null>(null);
	// svelte-ignore state_referenced_locally
	let style = $state(`left: ${x}px; top: ${y}px;`);

	$effect(() => {
		if (!menuEl) return;
		const rect = menuEl.getBoundingClientRect();
		const maxLeft = window.innerWidth - rect.width - 12;
		const maxTop = window.innerHeight - rect.height - 12;
		const left = Math.min(x, Math.max(12, maxLeft));
		const top = Math.min(y, Math.max(12, maxTop));
		style = `left: ${left}px; top: ${top}px;`;
	});

	function handleWindowPointerDown(e: PointerEvent) {
		if (menuEl && e.target instanceof Node && !menuEl.contains(e.target)) onClose();
	}

	function handleWindowKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}

	const isLive = $derived.by(() => {
		if (airing.start == null || airing.end == null) return false;
		const now = Date.now() / 1000;
		return now >= airing.start && now < airing.end;
	});

	const effectiveIsHd = $derived(isHd || airing.is_hd || false);

	function formatTime(seconds: number | null): string {
		if (seconds === null) return '';
		return new Date(seconds * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	}

	function formatTimeSpan(start: number | null, end: number | null): string {
		if (start === null) return '';
		const startDate = new Date(start * 1000);
		const startOfToday = new Date();
		startOfToday.setHours(0, 0, 0, 0);
		const diffDays = Math.round((startDate.getTime() - startOfToday.getTime()) / (86400 * 1000));

		let dayStr = '';
		if (diffDays === 0) {
			dayStr = $_('hdhomerun.detail.guide_today');
		} else if (diffDays === 1) {
			dayStr = $_('hdhomerun.detail.guide_tomorrow');
		} else {
			dayStr = startDate.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
		}

		const timeSpan = formatTime(start) + (end !== null ? ` – ${formatTime(end)}` : '');
		const durationMin = end !== null && start !== null ? Math.round((end - start) / 60) : null;
		const durationStr = durationMin ? ` (${durationMin} min)` : '';
		return `${dayStr} · ${timeSpan}${durationStr}`;
	}

	function formatEpisodeHeader(a: HDHomeRunGuideEntry): string {
		const parts: string[] = [];
		if (a.season_number && a.episode_number) {
			const epNum = a.episode_number.includes('.') ? a.episode_number.split('.')[1] : a.episode_number;
			parts.push(`S${a.season_number}E${epNum}`);
		} else if (a.episode_number) {
			if (a.episode_number.includes('.')) {
				const [s, e] = a.episode_number.split('.');
				parts.push(`S${s}E${e}`);
			} else {
				parts.push(`Ep ${a.episode_number}`);
			}
		}
		if (a.episode_title) {
			parts.push(a.episode_title);
		}
		return parts.join(' • ');
	}

	function formatAudio(audio: string): string {
		const lower = audio.toLowerCase().trim();
		if (lower === 'stereo') return 'STEREO';
		if (lower.includes('5.1')) return '5.1';
		if (lower.includes('dolby') || lower.includes('dd')) return 'DOLBY';
		if (lower === 'mono') return 'MONO';
		return audio.toUpperCase();
	}
</script>

<svelte:window onpointerdown={handleWindowPointerDown} onkeydown={handleWindowKeydown} />

<div class="menu-backdrop" onclick={onClose} onkeydown={(e) => e.key === 'Escape' && onClose()} role="presentation"></div>
<div class="cell-menu" bind:this={menuEl} {style} role="menu">
	<div class="menu-header">
		<div class="channel-chip">
			{#if channelNumber}
				<span class="chip-number">{channelNumber}</span>
			{/if}
			{#if channelName}
				<span class="chip-name">{channelName}</span>
			{/if}
			{#if effectiveIsHd}
				<span class="badge hd-badge">HD</span>
			{/if}
		</div>
		<span class="menu-title">{airing.title}</span>
		{#if formatEpisodeHeader(airing)}
			<span class="menu-episode">{formatEpisodeHeader(airing)}</span>
		{/if}
	</div>

	<div class="badges-row">
		{#if isLive}
			<span class="badge live-badge">{$_('hdhomerun.detail.live_badge')}</span>
		{/if}
		{#if airing.is_new}
			<span class="badge new-badge">{$_('hdhomerun.detail.new_badge')}</span>
		{/if}
		{#if effectiveIsHd}
			<span class="badge feature-badge">HD</span>
		{/if}
		{#if airing.has_cc !== false}
			<span class="badge feature-badge">CC</span>
		{/if}
		{#if airing.audio}
			<span class="badge feature-badge">{formatAudio(airing.audio)}</span>
		{/if}
		{#if airing.category}
			{#each airing.category.split(',').map((c) => c.trim()).filter(Boolean) as cat}
				<span class="badge category-badge">{cat}</span>
			{/each}
		{/if}
	</div>

	{#if airing.start != null}
		<div class="time-text">{formatTimeSpan(airing.start, airing.end)}</div>
	{/if}

	{#if airing.synopsis}
		<div class="menu-synopsis">{airing.synopsis}</div>
	{/if}

	<div class="menu-actions">
		{#if isLive && onWatch}
			<button class="menu-item watch" onclick={() => { onWatch?.(); onClose(); }} role="menuitem">
				▶ {$_('hdhomerun.detail.watch_button')}
			</button>
		{/if}

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
			<button class="menu-item primary" disabled={loading} onclick={onRecordEpisode} role="menuitem">
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
		width: 18rem;
		max-width: calc(100vw - 24px);
		max-height: calc(100vh - 24px);
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.65rem;
		box-shadow: 0 0.75rem 2rem rgba(0, 0, 0, 0.4);
		padding: 0.6rem;
		gap: 0.4rem;
	}

	.menu-header {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}

	.channel-chip {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
		margin-bottom: 0.1rem;
	}

	.chip-number {
		font-weight: 700;
		color: var(--color-primary);
	}

	.chip-name {
		font-weight: 500;
	}

	.menu-title {
		font-weight: 700;
		font-size: 0.95rem;
		line-height: 1.25;
		color: var(--color-text);
	}

	.menu-episode {
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--color-primary, #60a5fa);
		line-height: 1.2;
	}

	.badges-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		align-items: center;
	}

	.badge {
		font-size: 0.65rem;
		font-weight: 700;
		padding: 0.1rem 0.3rem;
		border-radius: 0.2rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		line-height: 1.2;
	}

	.hd-badge,
	.feature-badge {
		background: rgba(255, 255, 255, 0.08);
		color: var(--color-text-muted);
		border: 1px solid var(--color-border);
	}

	.live-badge {
		background: #dc2626;
		color: #ffffff;
	}

	.new-badge {
		background: rgba(16, 185, 129, 0.2);
		color: #10b981;
		border: 1px solid rgba(16, 185, 129, 0.3);
	}

	.category-badge {
		background: rgba(255, 255, 255, 0.05);
		color: var(--color-text-muted);
		border: 1px solid var(--color-border);
		text-transform: capitalize;
		font-weight: 500;
	}

	.time-text {
		font-size: 0.72rem;
		color: var(--color-text-muted);
		line-height: 1.2;
	}

	.menu-synopsis {
		font-size: 0.78rem;
		line-height: 1.35;
		color: var(--color-text-muted);
		display: -webkit-box;
		-webkit-line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
		text-overflow: ellipsis;
		padding: 0.15rem 0;
	}

	.menu-actions {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		margin-top: 0.2rem;
		border-top: 1px solid var(--color-border);
		padding-top: 0.35rem;
	}

	.menu-item {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		background: none;
		border: none;
		border-radius: 0.35rem;
		padding: 0.45rem 0.55rem;
		font-size: 0.82rem;
		font-weight: 500;
		color: var(--color-text);
		text-align: left;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.menu-item:hover:not(:disabled) {
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.08));
	}

	.menu-item.primary {
		color: var(--color-primary, #60a5fa);
	}

	.menu-item.watch {
		color: #10b981;
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
		padding: 0.1rem 0.6rem 0.2rem;
	}
</style>
