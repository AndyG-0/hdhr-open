<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type {
		HDHomeRunChannel,
		HDHomeRunFullGuideChannel,
		HDHomeRunGuideEntry,
		HDHomeRunRecordingRule,
		RecordingRuleOptions,
	} from '$lib/api';
	import { buildRecordingRuleIndex, findMatchingRecordingRuleIndexed } from '$lib/recording-rules';
	import HDHomeRunGuideCellMenu from './HDHomeRunGuideCellMenu.svelte';
	import HDHomeRunRecordingOptionsDialog from './HDHomeRunRecordingOptionsDialog.svelte';

	interface Props {
		channels: HDHomeRunChannel[];
		fullGuide: HDHomeRunFullGuideChannel[] | null;
		recordingRules: HDHomeRunRecordingRule[];
		pendingRuleIds: Set<string>;
		favoriteChannels: Set<string>;
		savingFavorite: boolean;
		recordingLoading: string | null;
		officialDvrActive: boolean;
		onWatch: (channel: HDHomeRunChannel) => void;
		onRecordEpisode: (
			seriesId: string | null | undefined,
			channelNumber: string,
			start: number | null,
			options?: RecordingRuleOptions,
		) => void;
		onRecordSeries: (seriesId: string, channelNumber: string, options?: RecordingRuleOptions) => void;
		onCancelRule: (ruleId: string) => void;
		onToggleFavorite: (channelNumber: string) => void;
	}

	let {
		channels,
		fullGuide,
		recordingRules,
		pendingRuleIds,
		favoriteChannels,
		savingFavorite,
		recordingLoading,
		officialDvrActive,
		onWatch,
		onRecordEpisode,
		onRecordSeries,
		onCancelRule,
		onToggleFavorite,
	}: Props = $props();

	const PX_PER_SEC = 4 / 60; // 4px per minute — a 30-minute slot is 120px wide.
	const MIN_CELL_WIDTH = 90;
	const HOUR_SECONDS = 3600;
	const DAY_SECONDS = 86400;

	let scrollEl = $state<HTMLDivElement | null>(null);
	let nowSeconds = $state(Math.floor(Date.now() / 1000));
	let hasAutoScrolled = false;

	// Vertical virtualization: only render channel rows within the scrolled
	// viewport (+ overscan). ROW_HEIGHT is a fixed estimate — acceptable
	// since .channel-name never wraps (nowrap + ellipsis), so rows are
	// effectively uniform height.
	const ROW_HEIGHT = 65;
	const OVERSCAN = 5;
	let scrollTop = $state(0);
	let viewportHeight = $state(0);

	function onGuideGridScroll(e: Event) {
		cancelPress();
		scrollTop = (e.currentTarget as HTMLElement).scrollTop;
	}

	$effect(() => {
		if (!scrollEl) return;
		const el = scrollEl;
		const ro = new ResizeObserver(() => {
			viewportHeight = el.clientHeight;
		});
		ro.observe(el);
		return () => ro.disconnect();
	});

	$effect(() => {
		const interval = setInterval(() => {
			nowSeconds = Math.floor(Date.now() / 1000);
		}, 30_000);
		return () => clearInterval(interval);
	});

	const guideByChannel = $derived.by(() => {
		const map = new Map<string, HDHomeRunFullGuideChannel>();
		for (const entry of fullGuide ?? []) map.set(entry.channel_number, entry);
		return map;
	});

	// Favorited channels first (their original relative order preserved),
	// then everything else — surfaces favorites without a duplicate section.
	const orderedChannels = $derived.by(() => {
		const favorites = channels.filter((c) => favoriteChannels.has(c.channel_number));
		const rest = channels.filter((c) => !favoriteChannels.has(c.channel_number));
		return [...favorites, ...rest];
	});

	let cachedWindowBounds = { start: 0, end: 0 };
	// Returns the same object reference when the computed bounds haven't
	// changed, so downstream $derived reads (hourMarks, dayMarks, per-row
	// cell layout) don't re-run on every 30s nowSeconds tick.
	const windowBounds = $derived.by(() => {
		let minStart = nowSeconds - 2 * HOUR_SECONDS;
		let maxEnd = nowSeconds + 4 * HOUR_SECONDS;
		const earliestAllowed = nowSeconds - 6 * HOUR_SECONDS;
		for (const entry of fullGuide ?? []) {
			for (const airing of entry.airings) {
				if (airing.start != null) minStart = Math.min(minStart, airing.start);
				if (airing.end != null) maxEnd = Math.max(maxEnd, airing.end);
			}
		}
		minStart = Math.max(minStart, earliestAllowed);
		// Align to the half hour for a cleaner ruler.
		const start = Math.floor(minStart / 1800) * 1800;
		if (start !== cachedWindowBounds.start || maxEnd !== cachedWindowBounds.end) {
			cachedWindowBounds = { start, end: maxEnd };
		}
		return cachedWindowBounds;
	});

	const hourMarks = $derived.by(() => {
		const { start, end } = windowBounds;
		const marks: { seconds: number; label: string }[] = [];
		let t = Math.ceil(start / HOUR_SECONDS) * HOUR_SECONDS;
		for (; t < end; t += HOUR_SECONDS) {
			marks.push({ seconds: t, label: new Date(t * 1000).toLocaleTimeString([], { hour: 'numeric' }) });
		}
		return marks;
	});

	function dayLabel(seconds: number): string {
		const date = new Date(seconds * 1000);
		const startOfToday = new Date();
		startOfToday.setHours(0, 0, 0, 0);
		const diffDays = Math.round((date.getTime() - startOfToday.getTime()) / (DAY_SECONDS * 1000));
		if (diffDays === 0) return $_('hdhomerun.detail.guide_today');
		if (diffDays === 1) return $_('hdhomerun.detail.guide_tomorrow');
		return date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
	}

	// Segments the ruler into local-midnight-to-midnight spans so each day
	// gets its own labeled header bar above the hour marks.
	const dayMarks = $derived.by(() => {
		const { start, end } = windowBounds;
		const marks: { seconds: number; left: number; width: number; label: string }[] = [];
		const firstDayStart = new Date(start * 1000);
		firstDayStart.setHours(0, 0, 0, 0);
		let t = Math.floor(firstDayStart.getTime() / 1000);
		while (t < end) {
			const nextDayStart = new Date(t * 1000);
			nextDayStart.setDate(nextDayStart.getDate() + 1);
			const nextT = Math.floor(nextDayStart.getTime() / 1000);
			const segStart = Math.max(t, start);
			const segEnd = Math.min(nextT, end);
			if (segEnd > segStart) {
				marks.push({
					seconds: segStart,
					left: (segStart - start) * PX_PER_SEC,
					width: (segEnd - segStart) * PX_PER_SEC,
					label: dayLabel(t),
				});
			}
			t = nextT;
		}
		return marks;
	});

	const totalWidth = $derived((windowBounds.end - windowBounds.start) * PX_PER_SEC);
	const nowLeft = $derived((nowSeconds - windowBounds.start) * PX_PER_SEC);

	interface CellLayout {
		airing: HDHomeRunGuideEntry;
		left: number;
		width: number;
	}

	function computeCellLayout(airings: HDHomeRunGuideEntry[], windowStart: number, windowEnd: number): CellLayout[] {
		const layouts: CellLayout[] = [];
		for (const airing of airings) {
			if (airing.start == null || airing.end == null) continue;
			const start = Math.max(airing.start, windowStart);
			const end = Math.min(airing.end, windowEnd);
			if (end <= start) continue;
			layouts.push({
				airing,
				left: (start - windowStart) * PX_PER_SEC,
				width: Math.max((end - start) * PX_PER_SEC, MIN_CELL_WIDTH),
			});
		}
		return layouts;
	}

	function mergeAiringsWithNowNext(
		guideAirings: HDHomeRunGuideEntry[],
		nowAiring?: HDHomeRunGuideEntry | null,
		nextAiring?: HDHomeRunGuideEntry | null,
	): HDHomeRunGuideEntry[] {
		const result = [...guideAirings];

		function overlaps(candidate: HDHomeRunGuideEntry): boolean {
			if (candidate.start == null || candidate.end == null) return false;
			return result.some(
				(a) => a.start != null && a.end != null && a.start < candidate.end! && a.end! > candidate.start!,
			);
		}

		if (nowAiring && nowAiring.start != null && nowAiring.end != null && !overlaps(nowAiring)) {
			result.push(nowAiring);
		}
		if (nextAiring && nextAiring.start != null && nextAiring.end != null && !overlaps(nextAiring)) {
			result.push(nextAiring);
		}

		return result.sort((a, b) => (a.start ?? 0) - (b.start ?? 0));
	}

	function isLive(airing: HDHomeRunGuideEntry): boolean {
		return airing.start != null && airing.end != null && airing.start <= nowSeconds && nowSeconds < airing.end;
	}

	const ruleIndex = $derived.by(() => buildRecordingRuleIndex(recordingRules));

	function findExistingRule(airing: HDHomeRunGuideEntry, channel: HDHomeRunChannel): HDHomeRunRecordingRule | null {
		return findMatchingRecordingRuleIndexed(ruleIndex, channel.channel_number, airing);
	}

	function isLoadingFor(
		airing: HDHomeRunGuideEntry,
		channel: HDHomeRunChannel,
		existingRule: HDHomeRunRecordingRule | null,
	) {
		if (existingRule) return recordingLoading === existingRule.RecordingRuleID;
		const targetId = airing.series_id || channel.channel_number;
		return recordingLoading === targetId;
	}

	let searchQuery = $state('');
	let highlightedCellKey = $state<string | null>(null);

	interface SearchResultItem {
		channel: HDHomeRunChannel;
		airing: HDHomeRunGuideEntry;
		isLive: boolean;
		isRecording: boolean;
		isPending: boolean;
	}

	function isAiringMatch(airing: HDHomeRunGuideEntry, channel: HDHomeRunChannel, q: string): boolean {
		if (!q) return false;
		if (airing.title?.toLowerCase().includes(q)) return true;
		if (airing.episode_title?.toLowerCase().includes(q)) return true;
		if (airing.synopsis?.toLowerCase().includes(q)) return true;
		if (channel.name?.toLowerCase().includes(q)) return true;
		if (channel.channel_number?.toLowerCase().includes(q)) return true;
		return false;
	}

	const searchResults = $derived.by(() => {
		const q = searchQuery.trim().toLowerCase();
		if (!q) return [];
		const results: SearchResultItem[] = [];
		const seenKeys = new Set<string>();

		for (const channel of channels) {
			const guideEntry = guideByChannel.get(channel.channel_number);
			const airings =
				guideEntry?.airings ?? (channel.now ? [channel.now, ...(channel.next ? [channel.next] : [])] : []);
			for (const airing of airings) {
				if (!isAiringMatch(airing, channel, q)) continue;
				const key = `${channel.channel_number}:${airing.start ?? airing.title}`;
				if (seenKeys.has(key)) continue;
				seenKeys.add(key);

				const rule = findExistingRule(airing, channel);
				results.push({
					channel,
					airing,
					isLive: isLive(airing),
					isRecording: rule !== null,
					isPending: rule !== null && pendingRuleIds.has(rule.RecordingRuleID),
				});
			}
		}

		return results.sort((a, b) => {
			if (a.isLive && !b.isLive) return -1;
			if (!a.isLive && b.isLive) return 1;
			const aStart = a.airing.start ?? Number.MAX_SAFE_INTEGER;
			const bStart = b.airing.start ?? Number.MAX_SAFE_INTEGER;
			return aStart - bStart;
		});
	});

	const matchingChannelNumbers = $derived.by(() => {
		const q = searchQuery.trim();
		if (!q) return null;
		return new Set(searchResults.map((r) => r.channel.channel_number));
	});

	const visibleChannels = $derived.by(() => {
		if (matchingChannelNumbers === null) return orderedChannels;
		return orderedChannels.filter((c) => matchingChannelNumbers.has(c.channel_number));
	});

	const visibleRange = $derived.by(() => {
		const total = visibleChannels.length;
		const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
		const end = Math.min(total, Math.ceil((scrollTop + viewportHeight) / ROW_HEIGHT) + OVERSCAN);
		return { start, end };
	});
	const windowedChannels = $derived(visibleChannels.slice(visibleRange.start, visibleRange.end));
	const topSpacerHeight = $derived(visibleRange.start * ROW_HEIGHT);
	const bottomSpacerHeight = $derived((visibleChannels.length - visibleRange.end) * ROW_HEIGHT);

	function scrollToAiring(airing: HDHomeRunGuideEntry, channel: HDHomeRunChannel) {
		if (!scrollEl || airing.start == null) return;
		const leftPx = (airing.start - windowBounds.start) * PX_PER_SEC;
		scrollEl.scrollTo({ left: Math.max(leftPx - 140, 0), behavior: 'smooth' });
		const key = `${channel.channel_number}:${airing.start ?? airing.title}`;
		highlightedCellKey = key;
		setTimeout(() => {
			if (highlightedCellKey === key) highlightedCellKey = null;
		}, 2500);
	}

	function formatSearchResultTime(start: number | null, end: number | null): string {
		if (start === null) return '';
		const startDate = new Date(start * 1000);
		const startOfToday = new Date();
		startOfToday.setHours(0, 0, 0, 0);
		const diffDays = Math.round((startDate.getTime() - startOfToday.getTime()) / (DAY_SECONDS * 1000));

		const timeSpan = formatCellTime(start) + (end !== null ? ` – ${formatCellTime(end)}` : '');
		if (diffDays === 0) return `${$_('hdhomerun.detail.guide_today')} · ${timeSpan}`;
		if (diffDays === 1) return `${$_('hdhomerun.detail.guide_tomorrow')} · ${timeSpan}`;
		const dayName = startDate.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
		return `${dayName} · ${timeSpan}`;
	}

	// Auto-scroll the timeline so "now" starts a little after the left edge,
	// once, the first time real guide data is available.
	$effect(() => {
		if (hasAutoScrolled || !scrollEl || !fullGuide) return;
		hasAutoScrolled = true;
		scrollEl.scrollLeft = Math.max(nowLeft - 60, 0);
	});

	let menuState = $state<{ airing: HDHomeRunGuideEntry; channel: HDHomeRunChannel; x: number; y: number } | null>(null);
	let optionsDialogState = $state<{ airing: HDHomeRunGuideEntry; channel: HDHomeRunChannel } | null>(null);

	function openContextMenu(airing: HDHomeRunGuideEntry, channel: HDHomeRunChannel, x: number, y: number) {
		menuState = { airing, channel, x, y };
	}

	function closeContextMenu() {
		menuState = null;
	}

	let pressTimer: ReturnType<typeof setTimeout> | null = null;
	let longPressFired = false;
	let pointerStart: { x: number; y: number } | null = null;
	const LONG_PRESS_MS = 500;
	const MOVE_CANCEL_PX = 10;

	function cancelPress() {
		if (pressTimer) clearTimeout(pressTimer);
		pressTimer = null;
		pointerStart = null;
	}

	function onCellPointerDown(e: PointerEvent, airing: HDHomeRunGuideEntry, channel: HDHomeRunChannel) {
		if (e.button !== undefined && e.button !== 0) return;
		pointerStart = { x: e.clientX, y: e.clientY };
		longPressFired = false;
		pressTimer = setTimeout(() => {
			longPressFired = true;
			openContextMenu(airing, channel, e.clientX, e.clientY);
		}, LONG_PRESS_MS);
	}

	function onCellPointerMove(e: PointerEvent) {
		if (!pointerStart || !pressTimer) return;
		if (
			Math.abs(e.clientX - pointerStart.x) > MOVE_CANCEL_PX ||
			Math.abs(e.clientY - pointerStart.y) > MOVE_CANCEL_PX
		) {
			cancelPress();
		}
	}

	function onCellClick(e: MouseEvent, airing: HDHomeRunGuideEntry, channel: HDHomeRunChannel) {
		if (longPressFired) {
			longPressFired = false;
			e.preventDefault();
			return;
		}
		if (isLive(airing)) {
			onWatch(channel);
		} else {
			openContextMenu(airing, channel, e.clientX, e.clientY);
		}
	}

	function onCellKeydown(e: KeyboardEvent, airing: HDHomeRunGuideEntry, channel: HDHomeRunChannel) {
		if (e.key !== 'Enter' && e.key !== ' ') return;
		e.preventDefault();
		const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
		if (isLive(airing)) {
			onWatch(channel);
		} else {
			openContextMenu(airing, channel, rect.left, rect.bottom);
		}
	}

	function formatCellTime(seconds: number | null): string {
		if (seconds === null) return '';
		return new Date(seconds * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	}
</script>

<div class="guide-toolbar">
	<div class="guide-search-wrapper">
		<span class="search-icon" aria-hidden="true">🔍</span>
		<input
			type="search"
			class="guide-search-input"
			placeholder={$_('hdhomerun.detail.search_placeholder')}
			bind:value={searchQuery}
			onkeydown={(e) => e.key === 'Escape' && (searchQuery = '')}
		/>
		{#if searchQuery}
			<button
				type="button"
				class="search-clear-btn"
				onclick={() => (searchQuery = '')}
				aria-label={$_('hdhomerun.detail.search_clear')}
			>
				✕
			</button>
		{/if}
	</div>
</div>

{#if searchQuery.trim()}
	<div class="search-results-panel">
		<div class="search-results-header">
			<span class="search-results-title">
				{$_('hdhomerun.detail.search_results_count', { values: { count: searchResults.length } })}
			</span>
			<button type="button" class="clear-search-link" onclick={() => (searchQuery = '')}>
				{$_('hdhomerun.detail.search_clear')}
			</button>
		</div>

		{#if searchResults.length > 0}
			<div class="search-results-list">
				{#each searchResults as item (item.channel.channel_number + ':' + (item.airing.start ?? item.airing.title))}
					<div class="search-result-card" class:live={item.isLive}>
						<div class="result-main">
							<div class="result-meta">
								{#if item.isLive}
									<span class="result-live-badge">{$_('hdhomerun.detail.search_live_badge')}</span>
								{/if}
								<span class="result-channel-badge">{item.channel.channel_number} {item.channel.name}</span>
								{#if item.airing.start != null}
									<span class="result-time">{formatSearchResultTime(item.airing.start, item.airing.end)}</span>
								{/if}
								{#if item.isPending}
									<span class="result-rec-badge result-rec-pending"
										>{$_('hdhomerun.detail.pending_recording_badge')}</span
									>
								{:else if item.isRecording}
									<span class="result-rec-badge">{$_('hdhomerun.tile.recording_badge')}</span>
								{/if}
							</div>
							<div class="result-title">{item.airing.title}</div>
							{#if item.airing.episode_title}
								<div class="result-subtitle">{item.airing.episode_title}</div>
							{/if}
							{#if item.airing.synopsis}
								<p class="result-synopsis">{item.airing.synopsis}</p>
							{/if}
						</div>
						<div class="result-actions">
							{#if item.isLive}
								<button type="button" class="result-btn watch-btn" onclick={() => onWatch(item.channel)}>
									{$_('hdhomerun.detail.watch_button')}
								</button>
							{/if}
							{#if item.airing.start != null}
								<button
									type="button"
									class="result-btn jump-btn"
									onclick={() => scrollToAiring(item.airing, item.channel)}
								>
									{$_('hdhomerun.detail.search_show_in_grid')}
								</button>
							{/if}
							<button
								type="button"
								class="result-btn more-btn"
								aria-label="Options"
								onclick={(e) => openContextMenu(item.airing, item.channel, e.clientX, e.clientY)}
							>
								⋯
							</button>
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<p class="search-empty">
				{$_('hdhomerun.detail.search_no_results', { values: { query: searchQuery } })}
			</p>
		{/if}
	</div>
{/if}

<div class="guide-grid" bind:this={scrollEl} onscroll={onGuideGridScroll}>
	<div class="grid-inner" style={`width: ${totalWidth + 160}px;`}>
		<div class="day-corner"></div>
		<div class="day-ruler" style={`width: ${totalWidth}px;`}>
			{#each dayMarks as mark (mark.seconds)}
				<div class="day-segment" style={`left: ${mark.left}px; width: ${mark.width}px;`}>
					<span class="day-label">{mark.label}</span>
				</div>
			{/each}
		</div>
		<div class="corner-cell"></div>
		<div class="time-ruler" style={`width: ${totalWidth}px;`}>
			{#each hourMarks as mark (mark.seconds)}
				<span class="hour-mark" style={`left: ${(mark.seconds - windowBounds.start) * PX_PER_SEC}px;`}>
					{mark.label}
				</span>
			{/each}
			<div class="now-line" style={`left: ${nowLeft}px;`}></div>
		</div>

		{#if topSpacerHeight > 0}
			<div class="row-spacer" style={`height: ${topSpacerHeight}px;`}></div>
		{/if}
		{#each windowedChannels as channel (channel.channel_number)}
			{@const guideEntry = guideByChannel.get(channel.channel_number)}
			{@const airings = mergeAiringsWithNowNext(guideEntry?.airings ?? [], channel.now, channel.next)}
			{@const cells = computeCellLayout(airings, windowBounds.start, windowBounds.end)}
			<div
				class="channel-col clickable"
				role="button"
				tabindex="0"
				onclick={() => onWatch(channel)}
				onkeydown={(e) => {
					if (e.key === 'Enter' || e.key === ' ') {
						e.preventDefault();
						onWatch(channel);
					}
				}}
			>
				<button
					type="button"
					class="favorite-toggle"
					class:active={favoriteChannels.has(channel.channel_number)}
					disabled={savingFavorite}
					onclick={(e) => {
						e.stopPropagation();
						onToggleFavorite(channel.channel_number);
					}}
					onkeydown={(e) => e.stopPropagation()}
					aria-label={favoriteChannels.has(channel.channel_number)
						? $_('hdhomerun.detail.remove_favorite')
						: $_('hdhomerun.detail.add_favorite')}
				>
					{favoriteChannels.has(channel.channel_number) ? '★' : '☆'}
				</button>
				<span class="channel-number">{channel.channel_number}</span>
				<span class="channel-name">{channel.name}</span>
				{#if channel.is_hd}<span class="badge">HD</span>{/if}
			</div>
			<div class="channel-track" style={`width: ${totalWidth}px;`}>
				<div class="now-line"></div>
				{#each cells as cell (cell.airing.start ?? cell.airing.title)}
					{@const existingRule = findExistingRule(cell.airing, channel)}
					{@const isMatch = searchQuery.trim()
						? isAiringMatch(cell.airing, channel, searchQuery.trim().toLowerCase())
						: false}
					{@const cellKey = `${channel.channel_number}:${cell.airing.start ?? cell.airing.title}`}
					<div
						class="airing-cell"
						class:live={isLive(cell.airing)}
						class:search-match={isMatch}
						class:search-dimmed={searchQuery.trim() && !isMatch}
						class:cell-flash={highlightedCellKey === cellKey}
						style={`left: ${cell.left}px; width: ${cell.width}px;`}
						role="button"
						tabindex="0"
						onpointerdown={(e) => onCellPointerDown(e, cell.airing, channel)}
						onpointermove={onCellPointerMove}
						onpointerup={cancelPress}
						onpointercancel={cancelPress}
						onpointerleave={cancelPress}
						onclick={(e) => onCellClick(e, cell.airing, channel)}
						onkeydown={(e) => onCellKeydown(e, cell.airing, channel)}
						oncontextmenu={(e) => e.preventDefault()}
					>
						<span class="cell-time" style={`max-width: ${Math.max(cell.width - 16, 0)}px;`}
							>{formatCellTime(cell.airing.start)}</span
						>
						<span class="cell-title" style={`max-width: ${Math.max(cell.width - 16, 0)}px;`}
							>{cell.airing.title}</span
						>
						{#if existingRule && pendingRuleIds.has(existingRule.RecordingRuleID)}
							<span class="cell-live-badge cell-pending-badge">{$_('hdhomerun.detail.pending_recording_badge')}</span>
						{:else if existingRule}
							<span class="cell-live-badge">{$_('hdhomerun.tile.recording_badge')}</span>
						{/if}
					</div>
				{/each}
			</div>
		{/each}
		{#if bottomSpacerHeight > 0}
			<div class="row-spacer" style={`height: ${bottomSpacerHeight}px;`}></div>
		{/if}
	</div>
</div>

{#if menuState}
	<HDHomeRunGuideCellMenu
		airing={menuState.airing}
		channelName={menuState.channel.name}
		x={menuState.x}
		y={menuState.y}
		existingRule={findExistingRule(menuState.airing, menuState.channel)}
		loading={isLoadingFor(menuState.airing, menuState.channel, findExistingRule(menuState.airing, menuState.channel))}
		pending={pendingRuleIds.has(findExistingRule(menuState.airing, menuState.channel)?.RecordingRuleID ?? '')}
		onRecordEpisode={() => {
			if (!menuState) return;
			onRecordEpisode(menuState.airing.series_id, menuState.channel.channel_number, menuState.airing.start);
			closeContextMenu();
		}}
		onRecordSeries={() => {
			if (!menuState || !menuState.airing.series_id) return;
			onRecordSeries(menuState.airing.series_id, menuState.channel.channel_number);
			closeContextMenu();
		}}
		onOpenOptions={() => {
			if (!menuState) return;
			optionsDialogState = { airing: menuState.airing, channel: menuState.channel };
			closeContextMenu();
		}}
		onCancelRule={(ruleId) => {
			onCancelRule(ruleId);
			closeContextMenu();
		}}
		onClose={closeContextMenu}
	/>
{/if}

{#if optionsDialogState}
	<HDHomeRunRecordingOptionsDialog
		airing={optionsDialogState.airing}
		channelName={optionsDialogState.channel.name}
		canRecordSeries={!!optionsDialogState.airing.series_id}
		{officialDvrActive}
		loading={isLoadingFor(
			optionsDialogState.airing,
			optionsDialogState.channel,
			findExistingRule(optionsDialogState.airing, optionsDialogState.channel),
		)}
		onConfirm={(mode, options) => {
			if (!optionsDialogState) return;
			if (mode === 'episode') {
				onRecordEpisode(
					optionsDialogState.airing.series_id,
					optionsDialogState.channel.channel_number,
					optionsDialogState.airing.start,
					options,
				);
			} else if (optionsDialogState.airing.series_id) {
				onRecordSeries(optionsDialogState.airing.series_id, optionsDialogState.channel.channel_number, options);
			}
			optionsDialogState = null;
		}}
		onClose={() => (optionsDialogState = null)}
	/>
{/if}

<style>
	.guide-toolbar {
		display: flex;
		align-items: center;
		margin: 0.75rem 0 0.5rem;
	}

	.guide-search-wrapper {
		position: relative;
		display: flex;
		align-items: center;
		max-width: 22rem;
		width: 100%;
	}

	.search-icon {
		position: absolute;
		left: 0.75rem;
		font-size: 0.85rem;
		color: var(--color-text-muted);
		pointer-events: none;
	}

	.guide-search-input {
		width: 100%;
		padding: 0.45rem 2rem 0.45rem 2.2rem;
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		background: var(--color-surface);
		color: var(--color-text);
		font: inherit;
		font-size: 0.88rem;
		transition: border-color 0.15s ease;
	}

	.guide-search-input:focus {
		outline: none;
		border-color: var(--color-accent);
	}

	.search-clear-btn {
		position: absolute;
		right: 0.5rem;
		background: none;
		border: none;
		color: var(--color-text-muted);
		padding: 0.2rem 0.4rem;
		font-size: 0.8rem;
		cursor: pointer;
		border-radius: 0.25rem;
	}

	.search-clear-btn:hover {
		color: var(--color-text);
	}

	.search-results-panel {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.search-results-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 0.5rem;
		padding-bottom: 0.4rem;
		border-bottom: 1px solid var(--color-border);
	}

	.search-results-title {
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--color-text-muted);
	}

	.clear-search-link {
		background: none;
		border: none;
		font-size: 0.8rem;
		color: var(--color-accent);
		cursor: pointer;
		padding: 0;
	}

	.search-results-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-height: 22rem;
		overflow-y: auto;
	}

	.search-result-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.6rem 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.45rem;
		transition:
			background 0.15s ease,
			border-color 0.15s ease;
	}

	.search-result-card:hover {
		border-color: var(--color-accent);
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.04));
	}

	.search-result-card.live {
		border-color: var(--color-accent);
	}

	.result-main {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		flex: 1;
		min-width: 0;
	}

	.result-meta {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-wrap: wrap;
		font-size: 0.78rem;
	}

	.result-live-badge {
		background: var(--color-error, #e05a5a);
		color: #fff;
		font-weight: 600;
		font-size: 0.68rem;
		padding: 0.1rem 0.35rem;
		border-radius: 0.25rem;
		text-transform: uppercase;
	}

	.result-channel-badge {
		font-weight: 600;
		color: var(--color-accent);
	}

	.result-time {
		color: var(--color-text-muted);
	}

	.result-rec-badge {
		color: var(--color-error, #e05a5a);
		font-weight: 600;
		font-size: 0.75rem;
	}

	.result-rec-pending {
		color: var(--color-warning, #d9a441);
	}

	.result-title {
		font-size: 0.92rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.result-subtitle {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.result-synopsis {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		margin: 0.1rem 0 0;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.result-actions {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-shrink: 0;
	}

	.result-btn {
		background: none;
		border: 1px solid var(--color-border);
		border-radius: 0.35rem;
		padding: 0.3rem 0.6rem;
		font-size: 0.78rem;
		color: var(--color-text);
		cursor: pointer;
		transition:
			background 0.15s ease,
			border-color 0.15s ease;
	}

	.result-btn:hover {
		border-color: var(--color-accent);
	}

	.result-btn.watch-btn {
		background: var(--color-accent);
		color: var(--color-surface);
		border-color: var(--color-accent);
		font-weight: 600;
	}

	.search-empty {
		color: var(--color-text-muted);
		font-size: 0.85rem;
		margin: 0.5rem 0;
		text-align: center;
	}

	.guide-grid {
		overflow: auto;
		overscroll-behavior-x: contain;
		border: 1px solid var(--color-border);
		border-radius: 0.75rem;
		margin: 0.5rem 0;
		max-height: 70vh;
	}

	.grid-inner {
		display: grid;
		grid-template-columns: 10rem 1fr;
		position: relative;
	}

	.day-corner {
		position: sticky;
		top: 0;
		left: 0;
		z-index: 6;
		height: 1.5rem;
		background: var(--color-surface);
		border-right: 1px solid var(--color-border);
		border-bottom: 1px solid var(--color-border);
	}

	.corner-cell {
		position: sticky;
		top: 1.5rem;
		left: 0;
		z-index: 4;
		background: var(--color-surface);
		border-right: 1px solid var(--color-border);
		border-bottom: 1px solid var(--color-border);
	}

	.day-ruler {
		position: sticky;
		top: 0;
		z-index: 5;
		height: 1.5rem;
		background: var(--color-surface);
		border-bottom: 1px solid var(--color-border);
	}

	.day-segment {
		position: absolute;
		top: 0;
		bottom: 0;
		border-left: 1px solid var(--color-border);
	}

	.day-label {
		position: sticky;
		left: 10rem;
		display: inline-flex;
		align-items: center;
		height: 1.5rem;
		max-width: calc(100% - 0.5rem);
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--color-text);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		padding-left: 0.5rem;
	}

	.time-ruler {
		position: sticky;
		top: 1.5rem;
		z-index: 3;
		height: 2rem;
		background: var(--color-surface);
		border-bottom: 1px solid var(--color-border);
	}

	.hour-mark {
		position: absolute;
		top: 0.4rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
		white-space: nowrap;
		padding-left: 0.25rem;
		border-left: 1px solid var(--color-border);
	}

	.row-spacer {
		grid-column: 1 / -1;
	}

	.channel-col {
		position: sticky;
		left: 0;
		z-index: 2;
		background: var(--color-surface);
		border-right: 1px solid var(--color-border);
		border-bottom: 1px solid var(--color-border);
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.35rem;
		padding: 0.5rem;
		min-height: 4rem;
	}

	.channel-col.clickable {
		cursor: pointer;
		user-select: none;
		transition:
			background 0.15s ease,
			border-color 0.15s ease;
	}

	.channel-col.clickable:hover {
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.05));
	}

	.channel-col.clickable:focus-visible {
		outline: 2px solid var(--color-accent);
		outline-offset: -2px;
	}

	.favorite-toggle {
		background: none;
		border: none;
		padding: 0;
		font-size: 1rem;
		line-height: 1;
		color: var(--color-text-muted);
		cursor: pointer;
	}

	.favorite-toggle.active {
		color: var(--color-accent);
	}

	.favorite-toggle:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.channel-number {
		color: var(--color-text-muted);
		font-size: 0.85rem;
	}

	.channel-name {
		font-weight: 600;
		font-size: 0.9rem;
		width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.badge {
		font-size: 0.7rem;
		border: 1px solid var(--color-accent);
		color: var(--color-accent);
		border-radius: 0.3rem;
		padding: 0.05rem 0.3rem;
	}

	.channel-track {
		position: relative;
		min-height: 4rem;
		border-bottom: 1px solid var(--color-border);
	}

	.now-line {
		position: absolute;
		top: 0;
		bottom: 0;
		width: 2px;
		background: var(--color-accent);
		z-index: 1;
		pointer-events: none;
	}

	.time-ruler .now-line {
		top: 0;
		bottom: -0.5rem;
	}

	.airing-cell {
		position: absolute;
		top: 0.35rem;
		bottom: 0.35rem;
		left: 0;
		display: flex;
		flex-direction: column;
		justify-content: center;
		gap: 0.1rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.4rem;
		padding: 0.25rem 0.5rem;
		cursor: pointer;
		user-select: none;
		touch-action: pan-y;
		transition:
			opacity 0.15s ease,
			box-shadow 0.15s ease;
	}

	.airing-cell.live {
		border-color: var(--color-accent);
		background: color-mix(in srgb, var(--color-accent) 12%, var(--color-surface));
	}

	.airing-cell.search-match {
		border-color: var(--color-accent);
		box-shadow: 0 0 0 1px var(--color-accent);
		z-index: 2;
	}

	.airing-cell.search-dimmed {
		opacity: 0.35;
	}

	.airing-cell.cell-flash {
		animation: cellFlashPulse 1.2s ease infinite;
		z-index: 3;
	}

	@keyframes cellFlashPulse {
		0%,
		100% {
			transform: scale(1);
			box-shadow: 0 0 0 2px var(--color-accent);
		}
		50% {
			transform: scale(1.04);
			box-shadow: 0 0 12px var(--color-accent);
		}
	}

	.cell-time {
		font-size: 0.7rem;
		color: var(--color-text-muted);
		position: sticky;
		left: 10rem;
		align-self: flex-start;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.cell-title {
		font-size: 0.8rem;
		font-weight: 600;
		position: sticky;
		left: 10rem;
		align-self: flex-start;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.cell-live-badge {
		font-size: 0.65rem;
		color: var(--color-error, #e05a5a);
		font-weight: 600;
	}

	.cell-pending-badge {
		color: var(--color-warning, #d9a441);
	}
</style>
