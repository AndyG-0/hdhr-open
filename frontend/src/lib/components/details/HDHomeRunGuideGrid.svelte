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
	import HDHomeRunCancelRuleModal from './HDHomeRunCancelRuleModal.svelte';
	import HDHomeRunFallbackConfirmModal from './HDHomeRunFallbackConfirmModal.svelte';
	import { isFallbackConfirmSuppressed, setFallbackConfirmSuppressed } from '$lib/fallback-confirm';

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
		onAddToMultiView?: (channel: HDHomeRunChannel) => void;
		onPopout?: (channel: HDHomeRunChannel) => void;
		onRecordEpisode: (
			seriesId: string | null | undefined,
			channelNumber: string,
			start: number | null,
			options?: RecordingRuleOptions,
		) => void;
		onRecordSeries: (seriesId: string, channelNumber: string, options?: RecordingRuleOptions) => void;
		onUpdateRule?: (ruleId: string, mode: 'episode' | 'series', options: RecordingRuleOptions) => void;
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
		onAddToMultiView,
		onPopout,
		onRecordEpisode,
		onRecordSeries,
		onUpdateRule,
		onCancelRule,
		onToggleFavorite,
	}: Props = $props();

	const PX_PER_SEC = 4 / 60; // 4px per minute — a 30-minute slot is 120px wide.
	const MIN_CELL_WIDTH = 90;
	const HOUR_SECONDS = 3600;
	const DAY_SECONDS = 86400;

	let scrollEl = $state<HTMLDivElement | null>(null);
	let shellEl = $state<HTMLDivElement | null>(null);
	let nowSeconds = $state(Math.floor(Date.now() / 1000));
	let hasAutoScrolled = false;

	// Vertical virtualization: only render channel rows within the scrolled
	// viewport (+ overscan). rowHeightPx (below, after isNarrowChannelCol is
	// defined) is a fixed estimate — acceptable since .channel-name never
	// wraps (nowrap + ellipsis), so rows are effectively uniform height. It
	// must track the actual CSS min-height of both .channel-col and
	// .channel-track (kept in sync with each other, including in narrow
	// mode) — using a single mismatched constant for both panes previously
	// caused them to drift apart while scrolling.
	const OVERSCAN = 5;
	let scrollTop = $state(0);
	let viewportHeight = $state(0);

	// Horizontal virtualization: only render airing cells within the
	// scrolled viewport (+ overscan) for each visible row. Without this,
	// every row would render a DOM node per airing across the whole fetched
	// guide window (up to ~14 days), which is thousands of nodes and the
	// cause of severe scroll jank/lockups on mobile.
	let scrollLeft = $state(0);
	let viewportWidth = $state(0);
	// Floor so overscan stays generous even when viewportWidth hasn't been
	// measured yet (e.g. jsdom in tests, where ResizeObserver is a no-op).
	const MIN_HORIZONTAL_OVERSCAN_PX = 600;

	// Channel column shrinks on narrow phones so more width goes to the guide
	// itself. Driven from JS (not a CSS media query) because the header/body
	// panes' total pixel width below must stay in exact sync with the column
	// width, or the 1fr track column ends up mis-sized. NARROW_VIEWPORT_PX
	// matches the 28.75rem breakpoint used elsewhere for mobile fixes.
	//
	// Measured off shellEl (the whole 4-quadrant component), not scrollEl —
	// scrollEl (the body pane) only spans the track/time area now that the
	// channel column and headers live in their own panes, so it no longer
	// reflects total device width the way the old single-scroller's
	// clientWidth did.
	const NARROW_VIEWPORT_PX = 460;
	// Call signs never run past ~7 chars (e.g. "KPNX-HD"), so 160px left a
	// visible gap wide enough for a second name - tightened to just fit the
	// name/number/badge column with a modest buffer.
	const CHANNEL_COL_WIDTH_PX = 112;
	const CHANNEL_COL_WIDTH_NARROW_PX = 80;
	let containerWidth = $state(0);
	const channelColWidthPx = $derived(
		containerWidth > 0 && containerWidth <= NARROW_VIEWPORT_PX ? CHANNEL_COL_WIDTH_NARROW_PX : CHANNEL_COL_WIDTH_PX,
	);
	const isNarrowChannelCol = $derived(channelColWidthPx === CHANNEL_COL_WIDTH_NARROW_PX);
	// Matches .channel-col / .channel-track min-height (4rem, or 3.25rem in
	// narrow mode) at a 16px root font size.
	const rowHeightPx = $derived(isNarrowChannelCol ? 52 : 64);

	// Batches scroll position updates to once per animation frame instead of
	// once per native `scroll` event (which can fire far more often than the
	// display refresh rate on some mobile browsers/trackpads). Without this,
	// every scroll tick synchronously re-runs the full derived chain below
	// (visibleRange, visibleTimeRange, and per-row cell layout), which is the
	// root cause of the guide becoming janky/unresponsive during a long
	// scroll session.
	let scrollRafId: number | null = null;
	let pendingScrollTop = 0;
	let pendingScrollLeft = 0;

	function onGuideGridScroll(e: Event) {
		cancelPress();
		const el = e.currentTarget as HTMLElement;
		pendingScrollTop = el.scrollTop;
		pendingScrollLeft = el.scrollLeft;
		if (scrollRafId === null) {
			scrollRafId = requestAnimationFrame(() => {
				scrollTop = pendingScrollTop;
				scrollLeft = pendingScrollLeft;
				scrollRafId = null;
			});
		}
	}

	$effect(() => {
		return () => {
			if (scrollRafId !== null) cancelAnimationFrame(scrollRafId);
		};
	});

	$effect(() => {
		if (!scrollEl) return;
		const el = scrollEl;
		const ro = new ResizeObserver(() => {
			viewportHeight = el.clientHeight;
			viewportWidth = el.clientWidth;
		});
		ro.observe(el);
		return () => ro.disconnect();
	});

	$effect(() => {
		if (!shellEl) return;
		const el = shellEl;
		const ro = new ResizeObserver(() => {
			containerWidth = el.clientWidth;
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

	// Simulates position:sticky for the day label as the user scrolls
	// horizontally, so "Today"/"Tomorrow"/etc. stays visible instead of only
	// showing at the very start of that day's segment. Real `position:
	// sticky` can't be used here because .pane-header-inner (the day/time
	// rulers' container) is repositioned via a CSS transform, not native
	// scrolling — sticky only responds to an actual scrolling ancestor. This
	// is cheap to compute (dayMarks is at most ~14 entries, one per day in
	// the fetched guide window) unlike the per-row/per-cell sticky this
	// component dropped for performance.
	const DAY_LABEL_RESERVE_PX = 100;
	function dayLabelLeft(mark: { left: number; width: number }): number {
		const scrolledIntoSegment = scrollLeft - mark.left;
		const maxOffset = Math.max(mark.width - DAY_LABEL_RESERVE_PX, 0);
		return Math.min(Math.max(scrolledIntoSegment, 0), maxOffset);
	}

	// The visible horizontal time-window (+ overscan), used to filter which
	// airings become DOM cells. Cell coordinates are still computed against
	// the full windowBounds (see computeCellLayout below), so this only
	// changes which airings are rendered, never where a rendered cell sits.
	const horizontalOverscanPx = $derived(Math.max(viewportWidth, MIN_HORIZONTAL_OVERSCAN_PX));
	const visibleTimeRange = $derived.by(() => {
		const { start, end } = windowBounds;
		const rangeStart = start + Math.max(scrollLeft - horizontalOverscanPx, 0) / PX_PER_SEC;
		const rangeEnd = start + (scrollLeft + viewportWidth + horizontalOverscanPx) / PX_PER_SEC;
		return { start: Math.max(rangeStart, start), end: Math.min(rangeEnd, end) };
	});

	function airingOverlapsRange(airing: HDHomeRunGuideEntry, start: number, end: number): boolean {
		return airing.start != null && airing.end != null && airing.start < end && airing.end > start;
	}

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

	// Per-row layout cache: without this, mergeAiringsWithNowNext +
	// computeCellLayout re-run for every windowed row on every scroll frame,
	// even though a given row's inputs (its airings + the visible time
	// window) usually haven't changed since the last frame. visibleTimeRange
	// is rounded to a coarse grain so small scroll deltas that don't change
	// which airings are relevant still hit the cache. The quantum is in
	// guide-time seconds, and PX_PER_SEC (4px/min) means 900 guide-seconds
	// is ~60 screen px — comfortably under the ≥600px horizontal overscan
	// buffer, so the cache still refreshes well before an unrendered airing
	// could become visible. (This used to be 30s, i.e. ~2 screen px — fine
	// grained enough that almost any real scroll motion invalidated every
	// visible row's cache on every animation frame, which was the actual
	// cause of the multi-second freeze during horizontal scrolling.)
	const ROW_CACHE_TIME_QUANTUM_SEC = 900;
	interface RowLayoutCacheEntry {
		airingsRef: HDHomeRunGuideEntry[] | undefined;
		nowRef: HDHomeRunGuideEntry | null | undefined;
		nextRef: HDHomeRunGuideEntry | null | undefined;
		timeKey: string;
		cells: CellLayout[];
	}
	const rowLayoutCache = new Map<string, RowLayoutCacheEntry>();

	function quantize(value: number): number {
		return Math.floor(value / ROW_CACHE_TIME_QUANTUM_SEC) * ROW_CACHE_TIME_QUANTUM_SEC;
	}

	function getRowCells(
		channelNumber: string,
		guideEntry: HDHomeRunFullGuideChannel | undefined,
		nowAiring: HDHomeRunGuideEntry | null | undefined,
		nextAiring: HDHomeRunGuideEntry | null | undefined,
	): CellLayout[] {
		const timeKey = `${quantize(visibleTimeRange.start)}|${quantize(visibleTimeRange.end)}|${windowBounds.start}|${windowBounds.end}`;
		const cached = rowLayoutCache.get(channelNumber);
		if (
			cached &&
			cached.airingsRef === guideEntry?.airings &&
			cached.nowRef === nowAiring &&
			cached.nextRef === nextAiring &&
			cached.timeKey === timeKey
		) {
			return cached.cells;
		}
		const airings = mergeAiringsWithNowNext(guideEntry?.airings ?? [], nowAiring, nextAiring);
		const visibleAirings = airings.filter((a) => airingOverlapsRange(a, visibleTimeRange.start, visibleTimeRange.end));
		const cells = computeCellLayout(visibleAirings, windowBounds.start, windowBounds.end);
		rowLayoutCache.set(channelNumber, {
			airingsRef: guideEntry?.airings,
			nowRef: nowAiring,
			nextRef: nextAiring,
			timeKey,
			cells,
		});
		return cells;
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
	let debouncedSearchQuery = $state('');
	let highlightedCellKey = $state<string | null>(null);

	$effect(() => {
		const q = searchQuery;
		if (!q.trim()) {
			debouncedSearchQuery = '';
			return;
		}
		const timer = setTimeout(() => {
			debouncedSearchQuery = q;
		}, 150);
		return () => clearTimeout(timer);
	});

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
		const q = debouncedSearchQuery.trim().toLowerCase();
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
		const q = debouncedSearchQuery.trim();
		if (!q) return null;
		return new Set(searchResults.map((r) => r.channel.channel_number));
	});

	const visibleChannels = $derived.by(() => {
		if (matchingChannelNumbers === null) return orderedChannels;
		return orderedChannels.filter((c) => matchingChannelNumbers.has(c.channel_number));
	});

	const visibleRange = $derived.by(() => {
		const total = visibleChannels.length;
		const start = Math.max(0, Math.floor(scrollTop / rowHeightPx) - OVERSCAN);
		const end = Math.min(total, Math.ceil((scrollTop + viewportHeight) / rowHeightPx) + OVERSCAN);
		return { start, end };
	});
	const windowedChannels = $derived(visibleChannels.slice(visibleRange.start, visibleRange.end));
	const topSpacerHeight = $derived(visibleRange.start * rowHeightPx);
	const bottomSpacerHeight = $derived((visibleChannels.length - visibleRange.end) * rowHeightPx);

	// Evict row-layout cache entries that have scrolled out of the windowed
	// range so the cache doesn't grow unbounded over a long session.
	$effect(() => {
		const visibleIds = new Set(windowedChannels.map((c) => c.channel_number));
		for (const key of rowLayoutCache.keys()) {
			if (!visibleIds.has(key)) rowLayoutCache.delete(key);
		}
	});

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

	// Jumps the guide so the given guide-window pixel offset starts a little
	// after the left edge. Used for the initial "now" auto-scroll, and by the
	// jump-to control (§4) for "now"/day selections. Sets `scrollLeft`
	// synchronously too — the native scroll event that would otherwise update
	// it fires asynchronously, which would briefly render cells near the
	// previous scroll position instead of the target on first paint.
	function scrollToLeftPx(targetLeft: number) {
		if (!scrollEl) return;
		const left = Math.max(targetLeft - 60, 0);
		scrollEl.scrollLeft = left;
		scrollLeft = left;
	}

	function scrollToNow() {
		scrollToLeftPx(nowLeft);
	}

	function scrollToDay(mark: { seconds: number; left: number }) {
		const isToday = mark.seconds === dayMarks[0]?.seconds;
		if (isToday) {
			scrollToNow();
		} else {
			scrollToLeftPx(mark.left);
		}
	}

	// Auto-scroll the timeline so "now" starts a little after the left edge,
	// once, the first time real guide data is available.
	$effect(() => {
		if (hasAutoScrolled || !scrollEl || !fullGuide) return;
		hasAutoScrolled = true;
		scrollToNow();
	});

	let menuState = $state<{ airing: HDHomeRunGuideEntry; channel: HDHomeRunChannel; x: number; y: number } | null>(null);
	let optionsDialogState = $state<{ airing: HDHomeRunGuideEntry; channel: HDHomeRunChannel } | null>(null);
	let fallbackConfirmTarget = $state<{
		mode: 'episode' | 'series';
		airing: HDHomeRunGuideEntry;
		channel: HDHomeRunChannel;
	} | null>(null);
	let ruleToCancelTarget = $state<{ ruleId: string; title: string } | null>(null);

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
			optionsDialogState = { airing, channel };
		}
	}

	function onCellKeydown(e: KeyboardEvent, airing: HDHomeRunGuideEntry, channel: HDHomeRunChannel) {
		if (e.key !== 'Enter' && e.key !== ' ') return;
		e.preventDefault();
		if (isLive(airing)) {
			onWatch(channel);
		} else {
			optionsDialogState = { airing, channel };
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
	{#if dayMarks.length > 0}
		<select
			class="guide-jump-select"
			aria-label={$_('hdhomerun.detail.jump_to_label')}
			onchange={(e) => {
				const target = dayMarks.find((mark) => String(mark.seconds) === e.currentTarget.value);
				if (target) scrollToDay(target);
				e.currentTarget.value = '';
			}}
		>
			<option value="" disabled selected>{$_('hdhomerun.detail.jump_to_label')}</option>
			{#each dayMarks as mark (mark.seconds)}
				<option value={mark.seconds}>{mark.label}</option>
			{/each}
		</select>
	{/if}
</div>

{#if debouncedSearchQuery.trim()}
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
								onclick={() => (optionsDialogState = { airing: item.airing, channel: item.channel })}
							>
								⋯
							</button>
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<p class="search-empty">
				{$_('hdhomerun.detail.search_no_results', { values: { query: debouncedSearchQuery } })}
			</p>
		{/if}
	</div>
{/if}

<div
	class="quadrant-shell"
	class:narrow-channel-col={isNarrowChannelCol}
	bind:this={shellEl}
	style={`--channel-col-width: ${channelColWidthPx}px;`}
>
	<div class="pane-corner">
		<div class="day-corner"></div>
		<div class="corner-cell"></div>
	</div>

	<div class="pane-header">
		<div class="pane-header-inner" style={`width: ${totalWidth}px; transform: translateX(${-scrollLeft}px);`}>
			<div class="day-ruler" style={`width: ${totalWidth}px;`}>
				{#each dayMarks as mark (mark.seconds)}
					<div class="day-segment" style={`left: ${mark.left}px; width: ${mark.width}px;`}>
						<span class="day-label" style={`left: ${dayLabelLeft(mark)}px;`}>{mark.label}</span>
					</div>
				{/each}
			</div>
			<div class="time-ruler" style={`width: ${totalWidth}px;`}>
				{#each hourMarks as mark (mark.seconds)}
					<span class="hour-mark" style={`left: ${(mark.seconds - windowBounds.start) * PX_PER_SEC}px;`}>
						{mark.label}
					</span>
				{/each}
				<div class="now-line" style={`left: ${nowLeft}px;`}></div>
			</div>
		</div>
	</div>

	<div class="pane-channels">
		<div class="pane-channels-inner" style={`transform: translateY(${-scrollTop}px);`}>
			{#if topSpacerHeight > 0}
				<div class="row-spacer" style={`height: ${topSpacerHeight}px;`}></div>
			{/if}
			{#each windowedChannels as channel (channel.channel_number)}
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
					{#if channel.is_hd}<span class="badge">HD</span>{/if}
					<span class="channel-name">{channel.name}</span>
				</div>
			{/each}
			{#if bottomSpacerHeight > 0}
				<div class="row-spacer" style={`height: ${bottomSpacerHeight}px;`}></div>
			{/if}
		</div>
	</div>

	<div class="pane-body" bind:this={scrollEl} onscroll={onGuideGridScroll}>
		<div class="pane-body-inner" style={`width: ${totalWidth}px;`}>
			{#if topSpacerHeight > 0}
				<div class="row-spacer" style={`height: ${topSpacerHeight}px;`}></div>
			{/if}
			{#each windowedChannels as channel (channel.channel_number)}
				{@const guideEntry = guideByChannel.get(channel.channel_number)}
				{@const cells = getRowCells(channel.channel_number, guideEntry, channel.now, channel.next)}
				<div class="channel-track" style={`width: ${totalWidth}px;`}>
					<div class="now-line" style={`left: ${nowLeft}px;`}></div>
					{#each cells as cell (cell.airing.start ?? cell.airing.title)}
						{@const existingRule = findExistingRule(cell.airing, channel)}
						{@const isMatch = debouncedSearchQuery.trim()
							? isAiringMatch(cell.airing, channel, debouncedSearchQuery.trim().toLowerCase())
							: false}
						{@const cellKey = `${channel.channel_number}:${cell.airing.start ?? cell.airing.title}`}
						<div
							class="airing-cell"
							class:live={isLive(cell.airing)}
							class:search-match={isMatch}
							class:search-dimmed={debouncedSearchQuery.trim() && !isMatch}
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
							<span class="cell-time">{formatCellTime(cell.airing.start)}</span>
							<span class="cell-title">{cell.airing.title}</span>
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
</div>

{#if menuState}
	<HDHomeRunGuideCellMenu
		airing={menuState.airing}
		channelName={menuState.channel.name}
		channelNumber={menuState.channel.channel_number}
		isHd={menuState.channel.is_hd}
		x={menuState.x}
		y={menuState.y}
		existingRule={findExistingRule(menuState.airing, menuState.channel)}
		loading={isLoadingFor(menuState.airing, menuState.channel, findExistingRule(menuState.airing, menuState.channel))}
		pending={pendingRuleIds.has(findExistingRule(menuState.airing, menuState.channel)?.RecordingRuleID ?? '')}
		onWatch={() => onWatch(menuState!.channel)}
		onAddToMultiView={onAddToMultiView ? () => onAddToMultiView?.(menuState!.channel) : undefined}
		onPopout={onPopout ? () => onPopout?.(menuState!.channel) : undefined}
		onRecordEpisode={() => {
			if (!menuState) return;
			const { airing, channel } = menuState;
			closeContextMenu();
			if (officialDvrActive && !airing.series_id && !isFallbackConfirmSuppressed()) {
				fallbackConfirmTarget = { mode: 'episode', airing, channel };
				return;
			}
			onRecordEpisode(airing.series_id, channel.channel_number, airing.start);
		}}
		onRecordSeries={() => {
			if (!menuState) return;
			const { airing, channel } = menuState;
			closeContextMenu();
			if (officialDvrActive && !airing.series_id && !isFallbackConfirmSuppressed()) {
				fallbackConfirmTarget = { mode: 'series', airing, channel };
				return;
			}
			onRecordSeries(airing.series_id || 'auto', channel.channel_number, {
				title: airing.title,
			});
		}}
		onOpenOptions={() => {
			if (!menuState) return;
			optionsDialogState = { airing: menuState.airing, channel: menuState.channel };
			closeContextMenu();
		}}
		onCancelRule={(ruleId) => {
			if (!menuState) return;
			const title = menuState.airing.title;
			closeContextMenu();
			ruleToCancelTarget = { ruleId, title };
		}}
		onClose={closeContextMenu}
	/>
{/if}

{#if fallbackConfirmTarget}
	<HDHomeRunFallbackConfirmModal
		title={fallbackConfirmTarget.airing.title}
		onConfirm={(dontAskAgain) => {
			if (dontAskAgain) setFallbackConfirmSuppressed(true);
			const target = fallbackConfirmTarget;
			fallbackConfirmTarget = null;
			if (!target) return;
			if (target.mode === 'episode') {
				onRecordEpisode(target.airing.series_id, target.channel.channel_number, target.airing.start);
			} else {
				onRecordSeries(target.airing.series_id || 'auto', target.channel.channel_number, {
					title: target.airing.title,
				});
			}
		}}
		onClose={() => (fallbackConfirmTarget = null)}
	/>
{/if}

{#if ruleToCancelTarget}
	<HDHomeRunCancelRuleModal
		title={ruleToCancelTarget.title}
		onConfirm={() => {
			const target = ruleToCancelTarget;
			ruleToCancelTarget = null;
			if (target) onCancelRule(target.ruleId);
		}}
		onClose={() => (ruleToCancelTarget = null)}
	/>
{/if}

{#if optionsDialogState}
	<HDHomeRunRecordingOptionsDialog
		airing={optionsDialogState.airing}
		channelName={optionsDialogState.channel.name}
		channelNumber={optionsDialogState.channel.channel_number}
		{channels}
		isHd={optionsDialogState.channel.is_hd}
		canRecordSeries={!!(optionsDialogState.airing.series_id || optionsDialogState.airing.title)}
		{officialDvrActive}
		existingRule={findExistingRule(optionsDialogState.airing, optionsDialogState.channel)}
		loading={isLoadingFor(
			optionsDialogState.airing,
			optionsDialogState.channel,
			findExistingRule(optionsDialogState.airing, optionsDialogState.channel),
		)}
		onWatch={() => onWatch(optionsDialogState!.channel)}
		onCancelRule={(ruleId) => {
			onCancelRule(ruleId);
			optionsDialogState = null;
		}}
		onConfirm={(mode, options) => {
			if (!optionsDialogState) return;
			const targetChannel = options?.channel !== undefined ? options.channel : optionsDialogState.channel.channel_number;
			if (mode === 'episode') {
				onRecordEpisode(
					optionsDialogState.airing.series_id,
					targetChannel,
					optionsDialogState.airing.start,
					options,
				);
			} else {
				onRecordSeries(
					optionsDialogState.airing.series_id || 'auto',
					targetChannel,
					options,
				);
			}
			optionsDialogState = null;
		}}
		onUpdateRule={(ruleId, mode, options) => {
			if (!optionsDialogState) return;
			if (onUpdateRule) {
				onUpdateRule(ruleId, mode, options);
			} else {
				const targetChannel = options?.channel !== undefined ? options.channel : optionsDialogState.channel.channel_number;
				if (mode === 'episode') {
					onRecordEpisode(
						optionsDialogState.airing.series_id,
						targetChannel,
						optionsDialogState.airing.start,
						options,
					);
				} else {
					onRecordSeries(
						optionsDialogState.airing.series_id || 'auto',
						targetChannel,
						options,
					);
				}
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
		gap: 0.5rem;
		margin: 0.75rem 0 0.5rem;
	}

	.guide-search-wrapper {
		position: relative;
		display: flex;
		align-items: center;
		max-width: 22rem;
		flex: 1;
	}

	.guide-jump-select {
		flex-shrink: 0;
		max-width: 8.5rem;
		padding: 0.45rem 0.5rem;
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		background: var(--color-surface);
		color: var(--color-text);
		font: inherit;
		font-size: 0.85rem;
	}

	.guide-jump-select:focus {
		outline: none;
		border-color: var(--color-accent);
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

	/* 4-quadrant frozen-pane layout: pane-corner/pane-header/pane-channels stay
	   visually fixed while only pane-body natively scrolls (both axes). The
	   header and channel-column panes are re-positioned via CSS transforms
	   driven by the same scrollTop/scrollLeft state already tracked for
	   pane-body's onscroll handler, instead of relying on position:sticky —
	   sticky's per-element recalculation cost (previously one sticky node per
	   visible row, plus two per visible airing cell) is what caused mobile
	   scroll jank that virtualization and rAF batching alone didn't fix. */
	.quadrant-shell {
		display: grid;
		grid-template-columns: var(--channel-col-width, 10rem) 1fr;
		grid-template-rows: 3.5rem 1fr;
		border: 1px solid var(--color-border);
		border-radius: 0.75rem;
		margin: 0.5rem 0;
		flex: 1;
		min-height: 0;
		overflow: hidden;
	}

	.pane-corner {
		position: relative;
		z-index: 3;
		background: var(--color-surface);
		border-right: 1px solid var(--color-border);
		border-bottom: 1px solid var(--color-border);
	}

	.pane-header {
		position: relative;
		overflow: hidden;
		z-index: 2;
		background: var(--color-surface);
		border-bottom: 1px solid var(--color-border);
	}

	.pane-header-inner {
		position: relative;
		will-change: transform;
	}

	.pane-channels {
		position: relative;
		overflow: hidden;
		z-index: 1;
		background: var(--color-surface);
		border-right: 1px solid var(--color-border);
	}

	.pane-channels-inner {
		will-change: transform;
	}

	.pane-body {
		overflow: auto;
		overscroll-behavior: contain;
		position: relative;
	}

	.pane-body-inner {
		position: relative;
	}

	.day-corner {
		height: 1.5rem;
		background: var(--color-surface);
		border-bottom: 1px solid var(--color-border);
	}

	.corner-cell {
		height: 2rem;
		background: var(--color-surface);
	}

	.day-ruler {
		position: relative;
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
		position: absolute;
		top: 0;
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
		position: relative;
		height: 2rem;
		background: var(--color-surface);
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

	.channel-col {
		background: var(--color-surface);
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

	/* On narrow phones the channel column shrinks (see channelColWidthPx in
	   script); there's no room left for the channel name or HD badge, so hide
	   them and keep only the number + favorite star legible. */
	.quadrant-shell.narrow-channel-col .channel-name,
	.quadrant-shell.narrow-channel-col .badge {
		display: none;
	}

	.quadrant-shell.narrow-channel-col .channel-col {
		padding: 0.35rem;
		gap: 0.2rem;
		min-height: 3.25rem;
	}

	.channel-track {
		position: relative;
		min-height: 4rem;
		border-bottom: 1px solid var(--color-border);
	}

	/* Must match .channel-col's narrow min-height above (and rowHeightPx in
	   the script) — otherwise the channel column and program grid rows fall
	   out of sync while scrolling. */
	.quadrant-shell.narrow-channel-col .channel-track {
		min-height: 3.25rem;
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
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.cell-title {
		font-size: 0.8rem;
		font-weight: 600;
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
