<script lang="ts">
	import {
		api,
		type HDHomeRunChannel,
		type HDHomeRunFullGuideChannel,
		type HDHomeRunGuideEntry,
		type HDHomeRunRecordingRule,
		type RecordingRuleOptions,
	} from '$lib/api';
	import HDHomeRunPlayer from '$lib/components/HDHomeRunPlayer.svelte';
	import HDHomeRunGuideGrid from '$lib/components/details/HDHomeRunGuideGrid.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';

	let channels = $state<HDHomeRunChannel[]>([]);
	let guideAvailable = $state(false);
	let tunerConfigured = $state(true);
	let loadingChannels = $state(true);
	let fullGuide = $state<HDHomeRunFullGuideChannel[] | null>(null);
	let loadingGuide = $state(false);

	let favoriteChannels = $state(new Set<string>());
	let savingFavorite = $state(false);
	let recordingLoading = $state<string | null>(null);
	let officialDvrActive = $state(false);
	let error = $state<string | null>(null);

	let playingMedia = $state<{
		title: string;
		url: string;
		playUrl: string;
		recordingId: string | null;
		// This viewer's own watch-session lifecycle token (heartbeat/stop/
		// promote) — distinct from recordingId, which identifies the shared
		// capture that other viewers/schedules may also be attached to.
		watchSessionId?: string | null;
		startTimestamp: number | null;
		recordEndTimestamp: number | null;
		seekable: boolean;
		isWatchSession?: boolean;
		channel?: HDHomeRunChannel | null;
		airing?: HDHomeRunGuideEntry | null;
	} | null>(null);

	// Heartbeat for the active live-watch auto-capture (see
	// backend/app/dvr/builtin/watch.py) — keeps it alive while the player is
	// open; DVREngine.tick() reaps captures that stop heartbeating.
	const WATCH_HEARTBEAT_INTERVAL_MS = 20_000;
	let watchHeartbeatHandle: ReturnType<typeof setInterval> | undefined;

	function stopWatchSession() {
		if (watchHeartbeatHandle !== undefined) {
			clearInterval(watchHeartbeatHandle);
			watchHeartbeatHandle = undefined;
		}
		if (playingMedia?.isWatchSession && playingMedia.watchSessionId) {
			api.stopWatch(playingMedia.watchSessionId);
		}
	}

	function closePlayer() {
		stopWatchSession();
		playingMedia = null;
	}

	// Backstop for a hard tab close/refresh, where component teardown
	// ordering (and thus onClose) isn't guaranteed to run.
	if (typeof window !== 'undefined') {
		window.addEventListener('pagehide', stopWatchSession);
		onDestroy(() => window.removeEventListener('pagehide', stopWatchSession));
	}

	interface PendingRule {
		rule: HDHomeRunRecordingRule;
		createdAt: number;
	}

	// SiliconDust's cloud recording_rules API is eventually consistent: a
	// rule created via one request sometimes isn't reflected yet in the very
	// next rules fetch. Track rules we know were just created (from the
	// mutation's own response) that a fresh fetch hasn't confirmed yet, so
	// they stay visible (flagged as pending) instead of appearing to
	// silently fail or vanish. Persisted so the pending flag survives a page
	// reload, since the vendor can take longer to catch up than the user
	// takes to navigate away and back.
	const PENDING_RULES_STORAGE_KEY = 'hdhomerun-pending-rules';
	const PENDING_RULE_MAX_AGE_MS = 30 * 60 * 1000;

	function loadPendingRules(): PendingRule[] {
		if (typeof localStorage === 'undefined') return [];
		try {
			const raw = localStorage.getItem(PENDING_RULES_STORAGE_KEY);
			if (!raw) return [];
			const parsed = JSON.parse(raw) as PendingRule[];
			const cutoff = Date.now() - PENDING_RULE_MAX_AGE_MS;
			return parsed.filter((p) => p.createdAt >= cutoff);
		} catch {
			return [];
		}
	}

	let recordingRules = $state<HDHomeRunRecordingRule[]>([]);
	let pendingRules = $state<PendingRule[]>(loadPendingRules());

	const pendingRuleIds = $derived(new Set(pendingRules.map((p) => p.rule.RecordingRuleID)));

	const displayedRecordingRules = $derived.by(() => {
		const realIds = new Set(recordingRules.map((r) => r.RecordingRuleID));
		return [...recordingRules, ...pendingRules.filter((p) => !realIds.has(p.rule.RecordingRuleID)).map((p) => p.rule)];
	});

	$effect(() => {
		if (typeof localStorage === 'undefined') return;
		if (pendingRules.length > 0) {
			localStorage.setItem(PENDING_RULES_STORAGE_KEY, JSON.stringify(pendingRules));
		} else {
			localStorage.removeItem(PENDING_RULES_STORAGE_KEY);
		}
	});

	async function loadChannels() {
		loadingChannels = true;
		try {
			const result = await api.getHDHomeRunChannels();
			channels = result.channels;
			guideAvailable = result.guide_available;
			tunerConfigured = true;
		} catch {
			tunerConfigured = false;
		} finally {
			loadingChannels = false;
		}
	}

	async function loadGuide() {
		if (fullGuide || loadingGuide) return;
		loadingGuide = true;
		try {
			fullGuide = await api.getHDHomeRunGuide();
		} catch {
			fullGuide = [];
		} finally {
			loadingGuide = false;
		}
	}

	async function loadFavorites() {
		try {
			const integration = await api.getNetworkIntegration('hdhomerun');
			const stored = integration.settings.favorite_channels;
			favoriteChannels = new Set(Array.isArray(stored) ? (stored as string[]) : []);
		} catch {
			// Favoriting is a nicety — leave the set empty on failure.
		}
	}

	async function loadRecordingRules() {
		try {
			recordingRules = await api.listRecordingRules();
		} catch {
			recordingRules = [];
		}
	}

	async function loadDvrInfo() {
		try {
			const info = await api.getDvrInfo();
			officialDvrActive = info.is_builtin === false;
		} catch {
			officialDvrActive = false;
		}
	}

	onMount(() => {
		loadChannels();
		loadGuide();
		loadFavorites();
		loadRecordingRules();
		loadDvrInfo();
	});

	async function watchChannel(channel: HDHomeRunChannel) {
		if (!channel.playback_url) {
			window.open(api.hdhomerunPlaylistUrl(channel.channel_number), '_blank');
			return;
		}

		const nowSec = Math.floor(Date.now() / 1000);
		const guideEntry = fullGuide?.find((g) => g.channel_number === channel.channel_number);
		const currentAiring =
			guideEntry?.airings.find((a) => a.start !== null && a.end !== null && a.start <= nowSec && a.end > nowSec) ??
			channel.now ??
			null;

		const title = `${channel.channel_number} ${channel.name}`;

		// Auto-start a hidden capture behind the channel so the player can
		// reuse the in-progress-recording playback path (pause/rewind/scrub).
		// Falls back to plain live playback below if no tuner is free.
		let watchRecording: {
			recording_id?: string | null;
			session_id?: string | null;
			play_url?: string | null;
			start?: number | null;
		} | null = null;
		try {
			watchRecording = await api.startWatch(channel.channel_number);
		} catch {
			// Fall back to plain live playback below.
		}

		if (watchRecording?.recording_id && watchRecording.session_id) {
			playingMedia = {
				title,
				url: api.hdhomerunPlaybackUrl(channel.playback_url),
				playUrl: watchRecording.play_url ?? channel.playback_url,
				recordingId: watchRecording.recording_id,
				watchSessionId: watchRecording.session_id,
				startTimestamp: watchRecording.start ?? nowSec,
				recordEndTimestamp: null,
				seekable: true,
				isWatchSession: true,
				channel,
				airing: currentAiring,
			};
			watchHeartbeatHandle = setInterval(() => {
				// Once promoted (Record hit mid-watch), the session is no longer
				// temporary and heartbeats become no-op 404s server-side - harmless,
				// just swallow them rather than let them surface as unhandled
				// rejections.
				if (playingMedia?.watchSessionId) api.heartbeatWatch(playingMedia.watchSessionId).catch(() => {});
			}, WATCH_HEARTBEAT_INTERVAL_MS);
			return;
		}

		playingMedia = {
			title,
			url: api.hdhomerunPlaybackUrl(channel.playback_url),
			playUrl: channel.playback_url,
			recordingId: null,
			startTimestamp: null,
			recordEndTimestamp: null,
			seekable: false,
			channel,
			airing: currentAiring,
		};
	}

	async function applyRuleMutation(mutate: () => Promise<HDHomeRunRecordingRule[]>) {
		const previousIds = new Set(recordingRules.map((r) => r.RecordingRuleID));
		const knownRules = await mutate();
		if (!Array.isArray(knownRules)) return;
		recordingRules = knownRules;
		const newlyCreated = knownRules.filter((r) => !previousIds.has(r.RecordingRuleID));

		await loadRecordingRules();

		const confirmedIds = new Set(recordingRules.map((r) => r.RecordingRuleID));
		const stillUnconfirmed = newlyCreated.filter((r) => !confirmedIds.has(r.RecordingRuleID));
		const createdAt = Date.now();
		pendingRules = [
			...pendingRules.filter((p) => !confirmedIds.has(p.rule.RecordingRuleID)),
			...stillUnconfirmed.map((rule) => ({ rule, createdAt })),
		];
	}

	async function recordShowEpisode(
		seriesId?: string | null,
		channelNumber?: string,
		startTime?: number | null,
		options?: RecordingRuleOptions,
	) {
		const targetId = seriesId || channelNumber || 'now';
		const effectiveChannel = options?.channel !== undefined ? options.channel : channelNumber;
		recordingLoading = targetId;
		try {
			await applyRuleMutation(() =>
				api.addHDHomeRunRecordingRule({
					series_id: seriesId || 'auto',
					channel: effectiveChannel,
					date_time: startTime ?? undefined,
					start_padding: options?.startPadding,
					end_padding: options?.endPadding,
					recent_only: options?.recentOnly,
					max_episodes_to_keep: options?.maxEpisodesToKeep,
					server: options?.server,
				}),
			);
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function recordShowSeries(seriesId: string, channelNumber?: string, options?: RecordingRuleOptions) {
		const targetId = seriesId || channelNumber || options?.title || 'series';
		const effectiveChannel = options?.channel !== undefined ? options.channel : channelNumber;
		recordingLoading = targetId;
		try {
			await applyRuleMutation(() =>
				api.addHDHomeRunRecordingRule({
					series_id: seriesId || 'auto',
					channel: effectiveChannel,
					title: options?.title,
					title_match_mode: options?.titleMatchMode,
					keyword_query: options?.keywordQuery,
					start_padding: options?.startPadding,
					end_padding: options?.endPadding,
					recent_only: options?.recentOnly,
					max_episodes_to_keep: options?.maxEpisodesToKeep,
					server: options?.server,
				}),
			);
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function cancelRecordingRule(ruleId: string) {
		recordingLoading = ruleId;
		try {
			pendingRules = pendingRules.filter((p) => p.rule.RecordingRuleID !== ruleId);
			await applyRuleMutation(() => api.deleteHDHomeRunRecordingRule(ruleId));
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function toggleFavorite(channelNumber: string) {
		const next = new Set(favoriteChannels);
		if (next.has(channelNumber)) {
			next.delete(channelNumber);
		} else {
			next.add(channelNumber);
		}
		favoriteChannels = next;
		savingFavorite = true;
		try {
			await api.updateNetworkIntegration('hdhomerun', { favorite_channels: [...next] });
		} finally {
			savingFavorite = false;
		}
	}
</script>

<div class="guide-page">
	{#if loadingChannels}
		<p class="hint">{$_('common.loading')}</p>
	{:else if !tunerConfigured}
		<p class="hint">{$_('hdhomerun.detail.not_connected_hint')}</p>
	{:else}
		{#if !guideAvailable}
			<p class="hint">{$_('hdhomerun.detail.guide_unavailable_hint')}</p>
		{/if}
		{#if error}
			<p class="hint error">{error}</p>
		{/if}
		<HDHomeRunGuideGrid
			{channels}
			{fullGuide}
			recordingRules={displayedRecordingRules}
			{pendingRuleIds}
			{favoriteChannels}
			{savingFavorite}
			{recordingLoading}
			{officialDvrActive}
			onWatch={watchChannel}
			onRecordEpisode={recordShowEpisode}
			onRecordSeries={recordShowSeries}
			onCancelRule={cancelRecordingRule}
			onToggleFavorite={toggleFavorite}
		/>
	{/if}
</div>

{#if playingMedia}
	<HDHomeRunPlayer
		src={playingMedia.url}
		title={playingMedia.title}
		playUrl={playingMedia.seekable ? playingMedia.playUrl : undefined}
		recordingId={playingMedia.seekable ? playingMedia.recordingId : undefined}
		watchSessionId={playingMedia.watchSessionId}
		startTimestamp={playingMedia.seekable ? playingMedia.startTimestamp : undefined}
		recordEndTimestamp={playingMedia.seekable ? playingMedia.recordEndTimestamp : undefined}
		seekable={playingMedia.seekable}
		isWatchSession={playingMedia.isWatchSession}
		channel={playingMedia.channel}
		airing={playingMedia.airing}
		{channels}
		recordingRules={displayedRecordingRules}
		{pendingRuleIds}
		{officialDvrActive}
		{recordingLoading}
		onRecordEpisode={recordShowEpisode}
		onRecordSeries={recordShowSeries}
		onCancelRule={cancelRecordingRule}
		onClose={closePlayer}
	/>
{/if}

<style>
	.guide-page {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.hint {
		color: var(--color-text-muted);
	}

	.hint.error {
		color: var(--color-error, #e05a5a);
	}
</style>
