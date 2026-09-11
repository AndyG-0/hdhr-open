<script lang="ts">
	import {
		api,
		type HDHomeRunChannel,
		type HDHomeRunFullGuideChannel,
		type HDHomeRunRecordingRule,
		type RecordingRuleOptions,
	} from '$lib/api';
	import HDHomeRunGuideGrid from '$lib/components/details/HDHomeRunGuideGrid.svelte';
	import { openPopoutPlayer } from '$lib/popout';
	import { onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { page } from '$app/state';
	import {
		playback,
		startPlayback,
		stopPlayback,
		useOwnedPlaybackContext,
		type PlaybackMedia,
	} from '$lib/stores/playback';
	import {
		buildEpisodeRulePayload,
		buildSeriesRulePayload,
		buildUpdateRulePayload,
		findNewFallbackRule,
	} from '$lib/recording-rule-actions';
	import { addFeed } from '$lib/stores/multiview';

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
	let fallbackNotice = $state<string | null>(null);

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

	function buildPlaybackContext() {
		return {
			channels,
			favoriteChannels,
			recordingRules: displayedRecordingRules,
			pendingRuleIds,
			officialDvrActive,
			recordingLoading,
			onRecordEpisode: recordShowEpisode,
			onRecordSeries: recordShowSeries,
			onUpdateRule: updateRecordingRule,
			onCancelRule: cancelRecordingRule,
			onToggleFavorite: toggleFavorite,
			onChannelChange: watchChannel,
			onToggleMultiView: () => {
				const current = get(playback);
				if (current.media?.channel) {
					const activeChannel = current.media.channel;
					stopPlayback();
					addFeed(activeChannel);
				}
			},
		};
	}

	useOwnedPlaybackContext(() => page.url.pathname, buildPlaybackContext);

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
			const media: PlaybackMedia = {
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
			startPlayback(media, page.url.pathname, buildPlaybackContext());
			return;
		}

		const media: PlaybackMedia = {
			title,
			url: api.hdhomerunPlaybackUrl(channel.playback_url),
			seekable: false,
			channel,
			airing: currentAiring,
		};
			startPlayback(media, page.url.pathname, buildPlaybackContext());
	}

	function popoutChannel(channel: HDHomeRunChannel) {
		stopPlayback();
		openPopoutPlayer({ channel: channel.channel_number, title: `${channel.channel_number} ${channel.name}` });
	}

	async function addToMultiView(channel: HDHomeRunChannel) {
		const currentPlayback = get(playback);
		if (currentPlayback.media?.channel) {
			const activeChannel = currentPlayback.media.channel;
			stopPlayback();
			await addFeed(activeChannel);
			await addFeed(channel);
			return;
		}
		if (currentPlayback.media) {
			stopPlayback();
		}
		await addFeed(channel);
	}

	async function applyRuleMutation(mutate: () => Promise<HDHomeRunRecordingRule[]>) {
		const previousIds = new Set(recordingRules.map((r) => r.RecordingRuleID));
		const knownRules = await mutate();
		if (!Array.isArray(knownRules)) return;
		recordingRules = knownRules;
		const newlyCreated = knownRules.filter((r) => !previousIds.has(r.RecordingRuleID));

		const fallbackRule = findNewFallbackRule(previousIds, knownRules);
		if (fallbackRule) {
			fallbackNotice = get(_)('hdhomerun.detail.fallback_notification', {
				values: { title: fallbackRule.Title || '' },
			});
		}

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
		error = null;
		const targetId = seriesId || channelNumber || 'now';
		recordingLoading = targetId;
		try {
			const payload = buildEpisodeRulePayload(seriesId, channelNumber, startTime, options);
			await applyRuleMutation(() => api.addHDHomeRunRecordingRule(payload));
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function recordShowSeries(seriesId: string, channelNumber?: string, options?: RecordingRuleOptions) {
		error = null;
		const targetId = seriesId || channelNumber || options?.title || 'series';
		recordingLoading = targetId;
		try {
			const payload = buildSeriesRulePayload(seriesId, channelNumber, options);
			await applyRuleMutation(() => api.addHDHomeRunRecordingRule(payload));
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function updateRecordingRule(
		ruleId: string,
		mode: 'episode' | 'series',
		options: RecordingRuleOptions,
	) {
		error = null;
		recordingLoading = ruleId;
		try {
			const payload = buildUpdateRulePayload(options);
			await applyRuleMutation(() => api.updateHDHomeRunRecordingRule(ruleId, payload));
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function cancelRecordingRule(ruleId: string) {
		error = null;
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
		{#if fallbackNotice}
			<div class="banner notice">
				<span>ℹ️ {fallbackNotice}</span>
				<button type="button" class="dismiss-notice-btn" onclick={() => (fallbackNotice = null)}>✕</button>
			</div>
		{/if}
		<HDHomeRunGuideGrid
			{channels}
			{fullGuide}
			recordingRules={displayedRecordingRules}
			{pendingRuleIds}
			{favoriteChannels}
			{savingFavorite}
			{recordingLoading}
			officialDvrActive={officialDvrActive}
			onWatch={watchChannel}
			onAddToMultiView={addToMultiView}
			onPopout={popoutChannel}
			onRecordEpisode={recordShowEpisode}
			onRecordSeries={recordShowSeries}
			onUpdateRule={updateRecordingRule}
			onCancelRule={cancelRecordingRule}
			onToggleFavorite={toggleFavorite}
		/>
	{/if}
</div>

<style>
	.guide-page {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-height: 0;
		gap: 0.5rem;
	}

	.hint {
		color: var(--color-text-muted);
	}

	.hint.error {
		color: var(--color-error, #e05a5a);
	}

	.banner.notice {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		background: rgba(74, 158, 218, 0.12);
		border: 1px solid rgba(74, 158, 218, 0.35);
		color: var(--color-text);
		padding: 0.6rem 0.9rem;
		border-radius: 0.5rem;
		margin-bottom: 0.75rem;
		font-size: 0.88rem;
	}

	.dismiss-notice-btn {
		background: transparent;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		font-size: 1rem;
		line-height: 1;
		padding: 0 0.25rem;
	}

	.dismiss-notice-btn:hover {
		color: var(--color-text);
	}
</style>
