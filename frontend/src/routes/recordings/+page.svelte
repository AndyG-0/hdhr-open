<script lang="ts">
	import {
		api,
		type HDHomeRunChannel,
		type HDHomeRunDvrInfo,
		type HDHomeRunRecording,
		type HDHomeRunRecordingRule,
		type HDHomeRunTuner,
		type HDHomeRunTunerInfo,
		type RecordingRuleOptions,
	} from '$lib/api';
	import RecordingCard from '$lib/components/RecordingCard.svelte';
	import { openPopoutPlayer } from '$lib/popout';
	import HDHomeRunKeywordRuleDialog, {
		type KeywordRuleOptions,
	} from '$lib/components/details/HDHomeRunKeywordRuleDialog.svelte';
	import HDHomeRunRecordingOptionsDialog from '$lib/components/details/HDHomeRunRecordingOptionsDialog.svelte';
	import HDHomeRunCancelRuleModal from '$lib/components/details/HDHomeRunCancelRuleModal.svelte';
	import TunerStatusPopover from '$lib/components/details/TunerStatusPopover.svelte';
	import { getCategoryType } from '$lib/recording-category';
	import {
		buildEpisodeRulePayload,
		buildSeriesRulePayload,
		buildUpdateRulePayload,
		findNewFallbackRule,
	} from '$lib/recording-rule-actions';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { page } from '$app/state';
	import {
		startPlayback,
		stopPlayback,
		useOwnedPlaybackContext,
		type PlaybackMedia,
	} from '$lib/stores/playback';

	let loading = $state(true);
	let tunerConfigured = $state(true);
	let dvrInfo = $state<HDHomeRunDvrInfo | null>(null);
	let recordingsInProgress = $state<HDHomeRunRecording[]>([]);
	let allRecordings = $state<HDHomeRunRecording[]>([]);
	const RECORDINGS_PAGE_SIZE = 30;
	let recordingsOffset = $state(0);
	let hasMoreRecordings = $state(true);
	let loadingMoreRecordings = $state(false);
	let recordingsSentinelEl = $state<HTMLDivElement | null>(null);
	let recordingRules = $state<HDHomeRunRecordingRule[]>([]);
	let editingRule = $state<HDHomeRunRecordingRule | null>(null);
	let channels = $state<HDHomeRunChannel[]>([]);
	let recordingLoading = $state<string | null>(null);
	let deletingRecordingId = $state<string | null>(null);
	let error = $state<string | null>(null);
	let fallbackNotice = $state<string | null>(null);
	let ruleToCancel = $state<HDHomeRunRecordingRule | null>(null);
	let playbackMode = $state('server_transcode');
	let tunerInfo = $state<HDHomeRunTunerInfo | null>(null);
	let tuners = $state<HDHomeRunTuner[]>([]);
	let tunerToTerminate = $state<HDHomeRunTuner | null>(null);
	let terminatingTunerIndex = $state<number | null>(null);
	let serverFilter = $state<'all' | 'builtin' | 'hdhomerun'>('all');
	let showKeywordRuleDialog = $state(false);
	let typeFilter = $state<'all' | 'shows' | 'movies' | 'sports'>('all');
	let failedImages = $state<Record<string, boolean>>({});

	const serverFilteredInProgress = $derived(
		recordingsInProgress.filter((r) => serverFilter === 'all' || (r.provider ?? 'builtin') === serverFilter),
	);
	const displayedRecordingsInProgress = $derived(
		serverFilteredInProgress.filter((r) => typeFilter === 'all' || getCategoryType(r) === typeFilter),
	);

	const serverFilteredRecordings = $derived(
		allRecordings.filter((r) => serverFilter === 'all' || (r.provider ?? 'builtin') === serverFilter),
	);

	const recordedShows = $derived(serverFilteredRecordings.filter((r) => getCategoryType(r) === 'shows'));
	const recordedMovies = $derived(serverFilteredRecordings.filter((r) => getCategoryType(r) === 'movies'));
	const recordedSports = $derived(serverFilteredRecordings.filter((r) => getCategoryType(r) === 'sports'));

	const categorySections = $derived([
		{
			id: 'shows',
			emoji: '📺',
			headingKey: 'hdhomerun.detail.recorded_shows',
			emptyKey: 'hdhomerun.detail.no_recorded_shows',
			items: recordedShows,
		},
		{
			id: 'movies',
			emoji: '🎬',
			headingKey: 'hdhomerun.detail.recorded_movies',
			emptyKey: 'hdhomerun.detail.no_recorded_movies',
			items: recordedMovies,
		},
		{
			id: 'sports',
			emoji: '🏆',
			headingKey: 'hdhomerun.detail.recorded_sports',
			emptyKey: 'hdhomerun.detail.no_recorded_sports',
			items: recordedSports,
		},
	]);

	const displayedRecordingRules = $derived(
		recordingRules.filter((r) => serverFilter === 'all' || ((r.provider ?? r.Provider) ?? 'builtin') === serverFilter),
	);

	// HDHomeRun-native recordings live in HDHomeRun's own storage, not ours -
	// this app has no way to delete them (see backend delete_recording, which
	// only handles builtin recordings), so the delete action must not be
	// offered for them.
	function canDeleteRecording(recording: HDHomeRunRecording): boolean {
		return (recording.provider ?? 'builtin') !== 'hdhomerun';
	}

	async function loadAll() {
		loading = true;
		try {
			const [dvr, recordings, rules, channelsResult, integration, tunerInfoResult, tunersResult] = await Promise.all([
				api.getDvrInfo().catch(() => null),
				api.listRecordings({ limit: RECORDINGS_PAGE_SIZE, offset: 0 }).catch(() => []),
				api.listRecordingRules().catch(() => []),
				api.getHDHomeRunChannels().catch(() => null),
				api.getNetworkIntegration('hdhomerun').catch(() => null),
				api.getTunerInfo().catch(() => null),
				api.getTunerStatus().catch(() => []),
			]);
			dvrInfo = dvr;
			tunerInfo = tunerInfoResult;
			tuners = tunersResult;
			if (integration && typeof integration.settings.playback_mode === 'string') {
				playbackMode = integration.settings.playback_mode;
			}
			const now = Date.now() / 1000;
			recordingsInProgress = recordings.filter((r) => r.record_end === null || r.record_end > now);
			allRecordings = recordings.filter((r) => r.record_end !== null && r.record_end <= now);
			recordingsOffset = recordings.length;
			hasMoreRecordings = recordings.length === RECORDINGS_PAGE_SIZE;
			recordingRules = rules;
			if (channelsResult) {
				channels = channelsResult.channels;
				tunerConfigured = true;
			} else {
				tunerConfigured = false;
			}
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		loadAll();
	});

	async function loadMoreRecordings() {
		if (loadingMoreRecordings || !hasMoreRecordings) return;
		loadingMoreRecordings = true;
		try {
			const page = await api.listRecordings({ limit: RECORDINGS_PAGE_SIZE, offset: recordingsOffset });
			const now = Date.now() / 1000;
			// Offset pagination can drift as recordings start/finish while the
			// user scrolls (an in-progress recording completing shifts every
			// later page by one row) — dedup by id guards against a recording
			// showing up twice across pages. Entries without a recording_id
			// (rare, some official-HDHomeRun-DVR rows) aren't deduped; an
			// accepted edge case rather than building a composite key for it.
			const knownIds = new Set(
				[...recordingsInProgress, ...allRecordings].map((r) => r.recording_id).filter((id) => id != null),
			);
			const fresh = page.filter((r) => r.recording_id == null || !knownIds.has(r.recording_id));
			recordingsInProgress = [
				...recordingsInProgress,
				...fresh.filter((r) => r.record_end === null || r.record_end > now),
			];
			allRecordings = [...allRecordings, ...fresh.filter((r) => r.record_end !== null && r.record_end <= now)];
			recordingsOffset += page.length;
			hasMoreRecordings = page.length === RECORDINGS_PAGE_SIZE;
		} catch {
			// Leave hasMoreRecordings as-is; the sentinel stays in view so the
			// next scroll/intersection tick simply retries.
		} finally {
			loadingMoreRecordings = false;
		}
	}

	$effect(() => {
		if (!recordingsSentinelEl) return;
		const el = recordingsSentinelEl;
		const io = new IntersectionObserver(
			(entries) => {
				if (entries[0]?.isIntersecting) loadMoreRecordings();
			},
			{ rootMargin: '400px' },
		);
		io.observe(el);
		return () => io.disconnect();
	});

	function handleTerminateTuner(tuner: HDHomeRunTuner) {
		error = null;
		tunerToTerminate = tuner;
	}

	async function confirmTerminateTuner() {
		if (!tunerToTerminate) return;
		error = null;
		const idx = tunerToTerminate.index;
		terminatingTunerIndex = idx;
		try {
			const res = await api.terminateTuner(idx);
			if (res.tuners) {
				tuners = res.tuners;
			} else {
				tuners = await api.getTunerStatus();
			}
			tunerToTerminate = null;
		} catch (err: unknown) {
			error = err instanceof Error ? err.message : 'Failed to terminate tuner';
		} finally {
			terminatingTunerIndex = null;
		}
	}

	function formatBytes(bytes: number | null): string {
		if (bytes === null) return get(_)('common.unknown');
		const gb = bytes / 1_000_000_000;
		return `${gb.toFixed(1)} GB`;
	}

	function formatDate(seconds: number | null): string {
		if (seconds === null) return '';
		return new Date(seconds * 1000).toLocaleString([], {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		});
	}

	function buildPlaybackContext() {
		return {
			channels,
			favoriteChannels: new Set<string>(),
			recordingRules: displayedRecordingRules,
			pendingRuleIds: new Set<string>(),
			officialDvrActive: dvrInfo?.is_builtin === false,
			recordingLoading,
			onRecordEpisode: recordShowEpisode,
			onRecordSeries: recordShowSeries,
			onUpdateRule: updateRuleFromDialog,
			onCancelRule: cancelRecordingRule,
		};
	}

	useOwnedPlaybackContext(() => page.url.pathname, buildPlaybackContext);

	function watchChannel(channel: HDHomeRunChannel) {
		if (channel.playback_url) {
			const media: PlaybackMedia = {
				title: `${channel.channel_number} ${channel.name}`,
				url: api.hdhomerunPlaybackUrl(channel.playback_url),
				seekable: false,
				channel,
				airing: channel.now ?? null,
			};
			startPlayback(media, page.url.pathname, buildPlaybackContext());
		} else {
			window.open(api.hdhomerunPlaylistUrl(channel.channel_number), '_blank');
		}
	}

	function playRecording(recording: HDHomeRunRecording) {
		let playUrl = recording.play_url;
		if (!playUrl && recording.recording_id) {
			playUrl = `/recorded/${recording.recording_id}`;
		}
		if (!playUrl && recording.channel_number) {
			playUrl = `/auto/v${recording.channel_number}`;
		}
		if (!playUrl) return;

		const seekable = recording.is_dvr_file === true && playbackMode === 'server_transcode';
		const streamUrl = api.hdhomerunRecordingStreamUrl(playUrl);

		const media: PlaybackMedia = {
			title: recording.episode_title ? `${recording.title} - ${recording.episode_title}` : recording.title,
			url: streamUrl,
			playUrl,
			recordingId: recording.recording_id ?? null,
			startTimestamp: recording.start,
			recordEndTimestamp: recording.record_end,
			seekable,
		};
		startPlayback(media, page.url.pathname, buildPlaybackContext());
	}

	function popoutRecording(recording: HDHomeRunRecording) {
		stopPlayback();
		let playUrl = recording.play_url;
		if (!playUrl && recording.recording_id) {
			playUrl = `/recorded/${recording.recording_id}`;
		}
		if (!playUrl && recording.channel_number) {
			playUrl = `/auto/v${recording.channel_number}`;
		}
		const title = recording.episode_title ? `${recording.title} - ${recording.episode_title}` : recording.title;
		openPopoutPlayer({
			recording: recording.recording_id ?? undefined,
			playUrl: playUrl ?? undefined,
			channel: recording.channel_number ?? undefined,
			title,
		});
	}

	function watchLiveForRecording(recording: HDHomeRunRecording) {
		if (!recording.channel_number) return;
		const channel = channels.find((c) => c.channel_number === recording.channel_number);
		if (channel) {
			watchChannel(channel);
		} else {
			const fallbackChannel: HDHomeRunChannel = {
				channel_number: recording.channel_number,
				name: recording.channel_name || recording.channel_number,
				is_hd: true,
				is_drm: false,
				stream_url: '',
				playback_url: null,
				now: null,
				next: null,
			};
			watchChannel(fallbackChannel);
		}
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
			const previousIds = new Set(recordingRules.map((r) => r.RecordingRuleID));
			const payload = buildEpisodeRulePayload(seriesId, channelNumber, startTime, options);
			const updated = await api.addHDHomeRunRecordingRule(payload);
			recordingRules = updated;
			const fallbackRule = findNewFallbackRule(previousIds, updated);
			if (fallbackRule) {
				fallbackNotice = get(_)('hdhomerun.detail.fallback_notification', {
					values: { title: fallbackRule.Title || '' },
				});
			}
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
			const previousIds = new Set(recordingRules.map((r) => r.RecordingRuleID));
			const payload = buildSeriesRulePayload(seriesId, channelNumber, options);
			const updated = await api.addHDHomeRunRecordingRule(payload);
			recordingRules = updated;
			const fallbackRule = findNewFallbackRule(previousIds, updated);
			if (fallbackRule) {
				fallbackNotice = get(_)('hdhomerun.detail.fallback_notification', {
					values: { title: fallbackRule.Title || '' },
				});
			}
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function createKeywordRule(options: KeywordRuleOptions) {
		error = null;
		recordingLoading = 'keyword-rule';
		try {
			recordingRules = await api.addHDHomeRunRecordingRule({
				series_id: 'auto',
				title: options.title,
				title_match_mode: options.titleMatchMode,
				keyword_query: options.keywordQuery,
				channel: options.channel,
				start_padding: options.startPadding,
				end_padding: options.endPadding,
				recent_only: options.recentOnly,
				max_episodes_to_keep: options.maxEpisodesToKeep,
				server: 'builtin',
			});
			showKeywordRuleDialog = false;
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
			recordingRules = await api.deleteHDHomeRunRecordingRule(ruleId);
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function updateRuleFromDialog(
		ruleId: string,
		mode: 'episode' | 'series',
		options: RecordingRuleOptions,
	) {
		error = null;
		recordingLoading = ruleId;
		try {
			const payload = buildUpdateRulePayload(options);
			recordingRules = await api.updateHDHomeRunRecordingRule(ruleId, payload);
			editingRule = null;
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			recordingLoading = null;
		}
	}

	async function deleteRecording(recording: HDHomeRunRecording) {
		const id = recording.recording_id;
		if (!id) return;
		error = null;
		deletingRecordingId = id;
		try {
			await api.deleteRecording(id);
			allRecordings = allRecordings.filter((r) => r.recording_id !== id);
		} catch (err) {
			error = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			deletingRecordingId = null;
		}
	}
</script>

<div class="recordings-page">
	{#if loading}
		<p class="hint">{$_('common.loading')}</p>
	{:else if !tunerConfigured}
		<p class="hint">{$_('hdhomerun.detail.not_connected_hint')}</p>
	{:else}
		{#if tunerInfo}
			<div class="tuner-info">
				<span>{tunerInfo.friendly_name}</span>
				{#if tunerInfo.model_number}<span>· {tunerInfo.model_number}</span>{/if}
				{#if tunerInfo.tuner_count}
					<span>·</span>
					<TunerStatusPopover
						{tuners}
						tunerCount={tunerInfo.tuner_count}
						onTerminateTuner={handleTerminateTuner}
					/>
				{/if}
			</div>
		{/if}

		<h1>{$_('hdhomerun.detail.dvr_section_heading')}</h1>
		{#if dvrInfo}
			<p class="hint">
				{$_('hdhomerun.detail.free_space', { values: { value: formatBytes(dvrInfo.free_space_bytes) } })}
			</p>
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

		<div class="filter-bars">
			<div class="server-filter-bar" role="group" aria-label={$_('hdhomerun.detail.server_label')}>
				<button
					type="button"
					class="filter-chip"
					class:active={serverFilter === 'all'}
					onclick={() => (serverFilter = 'all')}
				>
					{$_('hdhomerun.detail.filter_all_servers')}
				</button>
				<button
					type="button"
					class="filter-chip"
					class:active={serverFilter === 'builtin'}
					onclick={() => (serverFilter = 'builtin')}
				>
					{$_('hdhomerun.detail.filter_builtin_server')}
				</button>
				<button
					type="button"
					class="filter-chip"
					class:active={serverFilter === 'hdhomerun'}
					onclick={() => (serverFilter = 'hdhomerun')}
				>
					{$_('hdhomerun.detail.filter_hdhomerun_server')}
				</button>
			</div>

			<div class="server-filter-bar type-filter-bar" role="group" aria-label={$_('hdhomerun.detail.filter_all_types')}>
				<button
					type="button"
					class="filter-chip"
					class:active={typeFilter === 'all'}
					onclick={() => (typeFilter = 'all')}
				>
					{$_('hdhomerun.detail.filter_all_types')} ({serverFilteredRecordings.length})
				</button>
				<button
					type="button"
					class="filter-chip"
					class:active={typeFilter === 'shows'}
					onclick={() => (typeFilter = 'shows')}
				>
					📺 {$_('hdhomerun.detail.filter_shows')} ({recordedShows.length})
				</button>
				<button
					type="button"
					class="filter-chip"
					class:active={typeFilter === 'movies'}
					onclick={() => (typeFilter = 'movies')}
				>
					🎬 {$_('hdhomerun.detail.filter_movies')} ({recordedMovies.length})
				</button>
				<button
					type="button"
					class="filter-chip"
					class:active={typeFilter === 'sports'}
					onclick={() => (typeFilter = 'sports')}
				>
					🏆 {$_('hdhomerun.detail.filter_sports')} ({recordedSports.length})
				</button>
			</div>
		</div>

		<h2>{$_('hdhomerun.detail.recordings_in_progress')}</h2>
		{#if displayedRecordingsInProgress.length > 0}
			<div class="recordings">
				{#each displayedRecordingsInProgress as recording, i (recording.recording_id ?? i)}
					<RecordingCard
						{recording}
						variant="in-progress"
						failed={failedImages[recording.recording_id ?? ''] ?? false}
						onImageError={() => {
							failedImages[recording.recording_id ?? ''] = true;
						}}
						onWatchLive={() => watchLiveForRecording(recording)}
						onPopout={() => popoutRecording(recording)}
					/>
				{/each}
			</div>
		{:else}
			<p class="hint">{$_('hdhomerun.detail.no_recordings')}</p>
		{/if}

		{#snippet recordingGrid(items: HDHomeRunRecording[])}
			<div class="recordings">
				{#each items as recording, i (recording.recording_id ?? i)}
					<RecordingCard
						{recording}
						variant="completed"
						failed={failedImages[recording.recording_id ?? ''] ?? false}
						onImageError={() => {
							failedImages[recording.recording_id ?? ''] = true;
						}}
						onPlay={() => playRecording(recording)}
						onPopout={() => popoutRecording(recording)}
						onDelete={canDeleteRecording(recording) ? () => deleteRecording(recording) : undefined}
						deleting={deletingRecordingId === recording.recording_id}
					/>
				{/each}
			</div>
		{/snippet}

		{#if typeFilter === 'all'}
			{#if serverFilteredRecordings.length > 0}
				<h2>{$_('hdhomerun.detail.recorded_programs')}</h2>
				{#each categorySections as cat (cat.id)}
					{#if cat.items.length > 0}
						<h3 class="category-heading">{cat.emoji} {$_(cat.headingKey)} ({cat.items.length})</h3>
						{@render recordingGrid(cat.items)}
					{/if}
				{/each}
			{/if}
		{:else}
			{#each categorySections.filter((c) => c.id === typeFilter) as cat (cat.id)}
				<h2>{cat.emoji} {$_(cat.headingKey)} ({cat.items.length})</h2>
				{#if cat.items.length > 0}
					{@render recordingGrid(cat.items)}
				{:else}
					<p class="hint">{$_(cat.emptyKey)}</p>
				{/if}
			{/each}
		{/if}

		<div class="recordings-sentinel" bind:this={recordingsSentinelEl}></div>
		{#if loadingMoreRecordings}
			<p class="hint">{$_('common.loading')}</p>
		{/if}

		<div class="section-header">
			<h2>{$_('hdhomerun.detail.scheduled_recordings')}</h2>
			<button class="new-keyword-rule-btn" onclick={() => (showKeywordRuleDialog = true)}>
				{$_('hdhomerun.detail.keyword_rule_new_button')}
			</button>
		</div>
		{#if displayedRecordingRules.length > 0}
			<div class="recording-rules">
				{#each displayedRecordingRules as rule (rule.RecordingRuleID)}
					<div class="rule-card">
						<div class="rule-title">{rule.Title}</div>
						<div class="rule-details">
							<span class="rule-server-badge {((rule.provider ?? rule.Provider) ?? 'builtin')}">
								{((rule.provider ?? rule.Provider) === 'hdhomerun')
									? $_('hdhomerun.detail.server_badge_hdhomerun')
									: $_('hdhomerun.detail.server_badge_builtin')}
							</span>
							{#if rule.fallback_reason || rule.FallbackReason}
								<span
									class="rule-badge fallback"
									title={rule.fallback_reason || rule.FallbackReason || $_('hdhomerun.detail.fallback_tooltip')}
								>
									{$_('hdhomerun.detail.fallback_badge')}
								</span>
							{/if}
							<span class="rule-badge">
								{rule.DateTimeOnly ? $_('hdhomerun.detail.single_airing_rule') : $_('hdhomerun.detail.series_rule')}
							</span>
							{#if rule.ChannelOnly}<span class="rule-channel">Ch: {rule.ChannelOnly}</span>{/if}
							{#if rule.DateTimeOnly}<span class="rule-time">{formatDate(rule.DateTimeOnly)}</span>{/if}
							{#if rule.StartPadding || rule.EndPadding}
								<span class="rule-padding">
									{$_('hdhomerun.detail.padding_summary', {
										values: { start: Math.round((rule.StartPadding ?? 0) / 60), end: Math.round((rule.EndPadding ?? 0) / 60) },
									})}
								</span>
							{/if}
							{#if rule.MaxEpisodesToKeep}
								<span class="rule-retention">
									{$_('hdhomerun.detail.retention_summary', { values: { count: rule.MaxEpisodesToKeep } })}
								</span>
							{/if}
							{#if rule.TitleMatchMode === 'contains'}
								<span class="rule-badge">{$_('hdhomerun.detail.keyword_rule_match_contains')}</span>
							{/if}
							{#if rule.KeywordQuery}
								<span class="rule-badge">
									{$_('hdhomerun.detail.keyword_rule_badge', { values: { keywords: rule.KeywordQuery } })}
								</span>
							{/if}
						</div>
						<div class="rule-card-actions">
							<button
								class="edit-rule-btn"
								disabled={recordingLoading === rule.RecordingRuleID}
								onclick={() => (editingRule = rule)}
							>
								⚙️ {$_('hdhomerun.detail.recording_options')}
							</button>
							<button
								class="cancel-rule-btn"
								disabled={recordingLoading === rule.RecordingRuleID}
								onclick={() => (ruleToCancel = rule)}
							>
								{$_('hdhomerun.detail.cancel_recording')}
							</button>
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<p class="hint">{$_('hdhomerun.detail.no_scheduled_recordings')}</p>
		{/if}
	{/if}
</div>

{#if editingRule}
	<HDHomeRunRecordingOptionsDialog
		airing={{
			title: editingRule.Title,
			episode_title: null,
			series_id: editingRule.SeriesID,
			start: editingRule.DateTimeOnly ?? null,
			end: null,
			channel_number: editingRule.ChannelOnly,
		}}
		channelName=""
		channelNumber={editingRule.ChannelOnly}
		{channels}
		canRecordSeries={Boolean(editingRule.SeriesID || editingRule.Title)}
		officialDvrActive={((editingRule.provider ?? editingRule.Provider) === 'hdhomerun')}
		existingRule={editingRule}
		loading={recordingLoading === editingRule.RecordingRuleID}
		onCancelRule={(ruleId) => {
			cancelRecordingRule(ruleId);
			editingRule = null;
		}}
		onConfirm={(mode, options) => {
			if (editingRule) updateRuleFromDialog(editingRule.RecordingRuleID, mode, options);
		}}
		onUpdateRule={(ruleId, mode, options) => updateRuleFromDialog(ruleId, mode, options)}
		onClose={() => (editingRule = null)}
	/>
{/if}

{#if showKeywordRuleDialog}
	<HDHomeRunKeywordRuleDialog
		channels={channels}
		loading={recordingLoading === 'keyword-rule'}
		onConfirm={createKeywordRule}
		onClose={() => (showKeywordRuleDialog = false)}
	/>
{/if}

{#if ruleToCancel}
	<HDHomeRunCancelRuleModal
		title={ruleToCancel.Title || ''}
		onConfirm={() => {
			const id = ruleToCancel?.RecordingRuleID;
			ruleToCancel = null;
			if (id) cancelRecordingRule(id);
		}}
		onClose={() => (ruleToCancel = null)}
	/>
{/if}

{#if tunerToTerminate}
	<div
		class="tuner-modal-backdrop"
		onclick={() => (tunerToTerminate = null)}
		onkeydown={(e) => e.key === 'Escape' && (tunerToTerminate = null)}
		role="dialog"
		aria-modal="true"
		tabindex="-1"
	>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<div
			class="tuner-modal-card"
			onclick={(e) => e.stopPropagation()}
			role="presentation"
		>
			<h3 class="tuner-modal-title">
				{$_('hdhomerun.detail.tuner_terminate_modal_title', { values: { index: tunerToTerminate.index } })}
			</h3>
			<div class="tuner-modal-body">
				{#if tunerToTerminate.warning}
					<div class="tuner-warning-callout" class:danger={tunerToTerminate.warning.severity === 'danger'}>
						<p>{tunerToTerminate.warning.message}</p>
					</div>
				{:else}
					<p>Are you sure you want to terminate this active tuner stream?</p>
				{/if}
			</div>
			<div class="tuner-modal-actions">
				<button
					type="button"
					class="button-secondary"
					disabled={terminatingTunerIndex !== null}
					onclick={() => (tunerToTerminate = null)}
				>
					{$_('hdhomerun.detail.tuner_terminate_modal_cancel')}
				</button>
				<button
					type="button"
					class="button-danger"
					disabled={terminatingTunerIndex !== null}
					onclick={confirmTerminateTuner}
				>
					{#if terminatingTunerIndex !== null}
						{$_('hdhomerun.detail.tuner_terminating')}
					{:else}
						{$_('hdhomerun.detail.tuner_terminate_modal_confirm')}
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.recordings-page {
		display: flex;
		flex-direction: column;
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

	.tuner-info {
		color: var(--color-text-muted);
		margin: 0 0 0.5rem;
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.35rem;
		font-size: 0.9rem;
	}

	.tuner-modal-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.65);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: 1rem;
	}

	.tuner-modal-card {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.75rem;
		max-width: 28rem;
		width: 100%;
		padding: 1.25rem;
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.tuner-modal-title {
		margin: 0;
		font-size: 1.15rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.tuner-modal-body {
		font-size: 0.9rem;
		color: var(--color-text);
		line-height: 1.4;
	}

	.tuner-warning-callout {
		padding: 0.75rem;
		border-radius: 0.5rem;
		background: rgba(229, 160, 13, 0.12);
		border: 1px solid rgba(229, 160, 13, 0.35);
		color: var(--color-text);
	}

	.tuner-warning-callout.danger {
		background: rgba(224, 90, 90, 0.12);
		border-color: rgba(224, 90, 90, 0.35);
	}

	.tuner-warning-callout p {
		margin: 0;
	}

	.tuner-modal-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
	}

	.tuner-modal-actions .button-secondary {
		padding: 0.45rem 0.9rem;
		border-radius: 0.375rem;
		background: transparent;
		border: 1px solid var(--color-border);
		color: var(--color-text);
		cursor: pointer;
	}

	.tuner-modal-actions .button-danger {
		padding: 0.45rem 0.9rem;
		border-radius: 0.375rem;
		background: #e05a5a;
		border: 1px solid #e05a5a;
		color: #fff;
		font-weight: 500;
		cursor: pointer;
	}

	.tuner-modal-actions .button-danger:disabled,
	.tuner-modal-actions .button-secondary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.recordings {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
		gap: 1rem;
		margin: 0.5rem 0 1.5rem;
	}

	.recording-rules {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin: 0.5rem 0 1.5rem;
	}

	.recordings-sentinel {
		min-height: 1px;
	}

	.section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
	}

	.new-keyword-rule-btn {
		background: var(--color-surface-hover, rgba(0, 0, 0, 0.05));
		border: 1px solid var(--color-border);
		border-radius: 0.4rem;
		padding: 0.4rem 0.75rem;
		font-size: 0.85rem;
		color: var(--color-text);
		cursor: pointer;
		white-space: nowrap;
	}

	.rule-card {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.6rem 0.85rem;
	}

	.rule-title {
		flex: 0 0 20rem;
		width: 20rem;
		font-weight: 600;
		white-space: normal;
		overflow-wrap: break-word;
	}

	@media (max-width: 30rem) {
		.rule-title {
			flex: 1 1 100%;
			width: 100%;
		}
	}

	.rule-details {
		display: flex;
		flex: 1 1 auto;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.rule-badge {
		border: 1px solid var(--color-border);
		border-radius: 0.3rem;
		padding: 0.1rem 0.35rem;
		font-size: 0.75rem;
	}

	.rule-badge.fallback {
		background: rgba(224, 160, 90, 0.15);
		color: var(--color-warning, #e0a05a);
		border-color: rgba(224, 160, 90, 0.4);
		font-weight: 600;
	}

	.rule-card-actions {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-shrink: 0;
	}

	.edit-rule-btn {
		flex-shrink: 0;
		background: none;
		border: 1px solid var(--color-border);
		color: var(--color-text);
		border-radius: 0.4rem;
		padding: 0.25rem 0.6rem;
		font-size: 0.8rem;
		cursor: pointer;
	}

	.cancel-rule-btn {
		flex-shrink: 0;
		background: none;
		border: 1px solid var(--color-border);
		color: var(--color-error, #e05a5a);
		border-radius: 0.4rem;
		padding: 0.25rem 0.6rem;
		font-size: 0.8rem;
		cursor: pointer;
	}

	.filter-bars {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin: 0.5rem 0 1rem;
	}

	.server-filter-bar {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.type-filter-bar {
		margin-top: -0.25rem;
	}

	.category-heading {
		font-size: 1.15rem;
		font-weight: 600;
		margin: 1.25rem 0 0.5rem;
		color: var(--color-text);
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.filter-chip {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		color: var(--color-text-muted);
		border-radius: 2rem;
		padding: 0.3rem 0.8rem;
		font-size: 0.82rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.filter-chip:hover {
		color: var(--color-text);
		border-color: var(--color-text-muted);
	}

	.filter-chip.active {
		background: var(--color-accent);
		color: var(--color-surface);
		border-color: var(--color-accent);
		font-weight: 500;
	}

	.rule-server-badge {
		font-size: 0.72rem;
		padding: 0.1rem 0.4rem;
		border-radius: 0.3rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		color: var(--color-text-muted);
	}

	.rule-server-badge.hdhomerun {
		border-color: var(--color-accent);
		color: var(--color-accent);
	}
</style>
