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
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { page } from '$app/state';
	import { playback, startPlayback, stopPlayback, updateContext, type PlaybackMedia } from '$lib/stores/playback';

	let loading = $state(true);
	let tunerConfigured = $state(true);
	let dvrInfo = $state<HDHomeRunDvrInfo | null>(null);
	let recordingsInProgress = $state<HDHomeRunRecording[]>([]);
	let allRecordings = $state<HDHomeRunRecording[]>([]);
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

	function getCategoryType(rec: HDHomeRunRecording): 'shows' | 'movies' | 'sports' {
		if (rec.category_type) return rec.category_type;
		const t = (rec.title || '').toLowerCase();
		const ep = (rec.episode_title || '').toLowerCase();
		const cat = (rec.category || '').toLowerCase();
		const sports = [
			'sport',
			'sports',
			'football',
			'basketball',
			'baseball',
			'hockey',
			'soccer',
			'golf',
			'tennis',
			'racing',
			'nascar',
			'formula 1',
			'f1',
			'olympics',
			'wrestling',
			'boxing',
			'mma',
			'ufc',
			'wwe',
			'nfl',
			'nba',
			'mlb',
			'nhl',
			'pga',
			'mls',
			'premier league',
			'champions league',
			'uefa',
			'fifa',
			'ncaa',
			'college football',
			'college basketball',
		];
		if (
			sports.some((k) => cat.includes(k) || t.includes(k)) ||
			ep.includes(' at ') ||
			ep.includes(' vs ') ||
			ep.includes(' vs. ') ||
			ep.includes(' @ ')
		) {
			return 'sports';
		}
		const movies = ['movie', 'feature film', 'film', 'cinema'];
		if (movies.some((k) => cat.includes(k) || t.includes(k))) {
			return 'movies';
		}
		return 'shows';
	}

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
				api.listRecordings().catch(() => []),
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

	function handleTerminateTuner(tuner: HDHomeRunTuner) {
		tunerToTerminate = tuner;
	}

	async function confirmTerminateTuner() {
		if (!tunerToTerminate) return;
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
		} catch (err: any) {
			error = err?.message || 'Failed to terminate tuner';
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

	// Keeps the persistent player's context (callbacks/data) fresh whenever
	// this page's own state changes, but only while this page is the one that
	// started playback - otherwise a background page's stale closures would
	// clobber the context another page just published.
	$effect(() => {
		void channels;
		void displayedRecordingRules;
		void dvrInfo;
		void recordingLoading;
		// Reads the store via get(), not $playback, so publishing a context
		// update below doesn't re-trigger this same effect (an infinite loop).
		const current = get(playback);
		if (current.media && current.originPath === page.url.pathname) {
			updateContext(buildPlaybackContext());
		}
	});

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
		const targetId = seriesId || channelNumber || 'now';
		const effectiveChannel = options?.channel !== undefined ? options.channel : channelNumber;
		recordingLoading = targetId;
		try {
			const previousIds = new Set(recordingRules.map((r) => r.RecordingRuleID));
			const updated = await api.addHDHomeRunRecordingRule({
				series_id: seriesId || 'auto',
				channel: effectiveChannel,
				date_time: startTime ?? undefined,
				title: options?.title,
				start_padding: options?.startPadding,
				end_padding: options?.endPadding,
				recent_only: options?.recentOnly,
				max_episodes_to_keep: options?.maxEpisodesToKeep,
				server: options?.server,
			});
			recordingRules = updated;
			const newlyCreated = updated.filter((r) => !previousIds.has(r.RecordingRuleID));
			const fallbackRule = newlyCreated.find((r) => r.fallback_reason || r.FallbackReason);
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
		const targetId = seriesId || channelNumber || options?.title || 'series';
		const effectiveChannel = options?.channel !== undefined ? options.channel : channelNumber;
		recordingLoading = targetId;
		try {
			const previousIds = new Set(recordingRules.map((r) => r.RecordingRuleID));
			const updated = await api.addHDHomeRunRecordingRule({
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
			});
			recordingRules = updated;
			const newlyCreated = updated.filter((r) => !previousIds.has(r.RecordingRuleID));
			const fallbackRule = newlyCreated.find((r) => r.fallback_reason || r.FallbackReason);
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
		recordingLoading = ruleId;
		try {
			recordingRules = await api.updateHDHomeRunRecordingRule(ruleId, {
				channel: options.channel,
				title: options.title,
				title_match_mode: options.titleMatchMode,
				keyword_query: options.keywordQuery,
				start_padding: options.startPadding,
				end_padding: options.endPadding,
				recent_only: options.recentOnly,
				max_episodes_to_keep: options.maxEpisodesToKeep,
				server: options.server,
			});
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
					<div
						class="tuner-count-container"
						tabindex="0"
						role="button"
						aria-haspopup="true"
						aria-label={$_('hdhomerun.detail.tuner_count', { values: { count: tunerInfo.tuner_count } })}
					>
						<span class="tuner-count-pill">
							{$_('hdhomerun.detail.tuner_count', { values: { count: tunerInfo.tuner_count } })}
							{#if tuners.some((t) => t.in_use)}
								<span class="tuner-active-dot" aria-hidden="true"></span>
							{/if}
						</span>
						<div class="tuner-status-popover" role="tooltip">
							<div class="tuner-status-header">{$_('hdhomerun.detail.tuner_status_heading')}</div>
							{#if tuners.length > 0}
								<ul class="tuner-status-list">
									{#each tuners as tuner (tuner.index)}
										<li class="tuner-status-row" class:in-use={tuner.in_use}>
											<div class="tuner-status-label-group">
												<span class="tuner-status-indicator" class:active={tuner.in_use}></span>
												<span class="tuner-status-name">
													{$_('hdhomerun.detail.tuner_label', { values: { index: tuner.index } })}
												</span>
											</div>
											<div class="tuner-status-details">
												{#if tuner.in_use}
													<span class="tuner-channel">
														{#if tuner.channel_number}<span class="tuner-ch-num">{tuner.channel_number}</span>{/if}
														{#if tuner.channel_name}<span class="tuner-ch-name">{tuner.channel_name}</span>{:else}<span
																class="tuner-in-use-tag">{$_('hdhomerun.detail.tuner_in_use')}</span
															>{/if}
													</span>
													{#if tuner.client}
														<span
															class="tuner-client-badge"
															class:external={tuner.client.type === 'external'}
															class:recording={tuner.client.is_recording}
															title={tuner.client.details}
														>
															{#if tuner.client.type === 'external'}
																{$_('hdhomerun.detail.tuner_client_external', { values: { ip: tuner.client.name } })}
															{:else}
																{$_('hdhomerun.detail.tuner_client_label', { values: { name: tuner.client.name } })}
															{/if}
														</span>
													{/if}
													{#if tuner.signal_strength_percent != null}
														<span class="tuner-signal">
															{$_('hdhomerun.detail.tuner_signal', {
																values: { percent: tuner.signal_strength_percent },
															})}
														</span>
													{/if}
													<button
														type="button"
														class="tuner-terminate-btn"
														aria-label={$_('hdhomerun.detail.tuner_terminate_button')}
														onclick={(e) => {
															e.stopPropagation();
															handleTerminateTuner(tuner);
														}}
													>
														{$_('hdhomerun.detail.tuner_terminate_button')}
													</button>
												{:else}
													<span class="tuner-idle">{$_('hdhomerun.detail.tuner_idle')}</span>
												{/if}
											</div>
										</li>
									{/each}
								</ul>
							{:else}
								<p class="tuner-status-empty">{$_('hdhomerun.detail.tuner_status_unavailable')}</p>
							{/if}
						</div>
					</div>
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

		{#if typeFilter === 'all'}
			{#if serverFilteredRecordings.length > 0}
				<h2>{$_('hdhomerun.detail.recorded_programs')}</h2>
				{#if recordedShows.length > 0}
					<h3 class="category-heading">📺 {$_('hdhomerun.detail.recorded_shows')} ({recordedShows.length})</h3>
					<div class="recordings">
						{#each recordedShows as recording, i (recording.recording_id ?? i)}
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
				{/if}
				{#if recordedMovies.length > 0}
					<h3 class="category-heading">🎬 {$_('hdhomerun.detail.recorded_movies')} ({recordedMovies.length})</h3>
					<div class="recordings">
						{#each recordedMovies as recording, i (recording.recording_id ?? i)}
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
				{/if}
				{#if recordedSports.length > 0}
					<h3 class="category-heading">🏆 {$_('hdhomerun.detail.recorded_sports')} ({recordedSports.length})</h3>
					<div class="recordings">
						{#each recordedSports as recording, i (recording.recording_id ?? i)}
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
				{/if}
			{/if}
		{:else if typeFilter === 'shows'}
			<h2>📺 {$_('hdhomerun.detail.recorded_shows')} ({recordedShows.length})</h2>
			{#if recordedShows.length > 0}
				<div class="recordings">
					{#each recordedShows as recording, i (recording.recording_id ?? i)}
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
			{:else}
				<p class="hint">{$_('hdhomerun.detail.no_recorded_shows')}</p>
			{/if}
		{:else if typeFilter === 'movies'}
			<h2>🎬 {$_('hdhomerun.detail.recorded_movies')} ({recordedMovies.length})</h2>
			{#if recordedMovies.length > 0}
				<div class="recordings">
					{#each recordedMovies as recording, i (recording.recording_id ?? i)}
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
			{:else}
				<p class="hint">{$_('hdhomerun.detail.no_recorded_movies')}</p>
			{/if}
		{:else if typeFilter === 'sports'}
			<h2>🏆 {$_('hdhomerun.detail.recorded_sports')} ({recordedSports.length})</h2>
			{#if recordedSports.length > 0}
				<div class="recordings">
					{#each recordedSports as recording, i (recording.recording_id ?? i)}
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
			{:else}
				<p class="hint">{$_('hdhomerun.detail.no_recorded_sports')}</p>
			{/if}
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

	.tuner-count-container {
		position: relative;
		display: inline-flex;
		align-items: center;
		outline: none;
	}

	.tuner-count-pill {
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		border-bottom: 1px dashed var(--color-text-muted);
		transition:
			color 0.15s ease,
			border-color 0.15s ease;
	}

	.tuner-count-container:hover .tuner-count-pill,
	.tuner-count-container:focus .tuner-count-pill,
	.tuner-count-container:focus-within .tuner-count-pill {
		color: var(--color-text);
		border-color: var(--color-accent);
	}

	.tuner-active-dot {
		width: 0.45rem;
		height: 0.45rem;
		border-radius: 50%;
		background: var(--color-success, #4caf50);
		box-shadow: 0 0 4px var(--color-success, #4caf50);
	}

	.tuner-status-popover {
		position: absolute;
		top: calc(100% + 0.4rem);
		left: 0;
		z-index: 10;
		min-width: 16rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.6rem 0.75rem;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
		opacity: 0;
		visibility: hidden;
		transform: translateY(4px);
		pointer-events: none;
		transition:
			opacity 0.15s ease,
			transform 0.15s ease,
			visibility 0.15s;
	}

	.tuner-count-container:hover .tuner-status-popover,
	.tuner-count-container:focus .tuner-status-popover,
	.tuner-count-container:focus-within .tuner-status-popover {
		opacity: 1;
		visibility: visible;
		transform: translateY(0);
		pointer-events: auto;
	}

	.tuner-status-header {
		font-weight: 600;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-text-muted);
		margin-bottom: 0.4rem;
		border-bottom: 1px solid var(--color-border);
		padding-bottom: 0.25rem;
	}

	.tuner-status-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.tuner-status-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		font-size: 0.82rem;
		padding: 0.2rem 0;
	}

	.tuner-status-label-group {
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}

	.tuner-status-indicator {
		width: 0.45rem;
		height: 0.45rem;
		border-radius: 50%;
		background: var(--color-text-muted);
		opacity: 0.4;
	}

	.tuner-status-indicator.active {
		background: var(--color-success, #4caf50);
		opacity: 1;
		box-shadow: 0 0 5px var(--color-success, #4caf50);
	}

	.tuner-status-name {
		font-weight: 500;
		color: var(--color-text);
	}

	.tuner-status-details {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.tuner-channel {
		color: var(--color-text);
		font-weight: 500;
	}

	.tuner-ch-num {
		color: var(--color-accent);
		margin-right: 0.2rem;
	}

	.tuner-in-use-tag {
		color: var(--color-accent);
	}

	.tuner-signal {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.tuner-idle {
		color: var(--color-text-muted);
		font-style: italic;
	}

	.tuner-client-badge {
		font-size: 0.72rem;
		padding: 0.1rem 0.35rem;
		border-radius: 0.25rem;
		background: var(--color-surface-variant, rgba(255, 255, 255, 0.08));
		color: var(--color-text);
		border: 1px solid var(--color-border);
		max-width: 10rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.tuner-client-badge.external {
		color: #e5a00d;
		border-color: rgba(229, 160, 13, 0.3);
		background: rgba(229, 160, 13, 0.1);
	}

	.tuner-client-badge.recording {
		color: #e05a5a;
		border-color: rgba(224, 90, 90, 0.3);
		background: rgba(224, 90, 90, 0.1);
	}

	.tuner-terminate-btn {
		font-size: 0.72rem;
		padding: 0.15rem 0.4rem;
		border-radius: 0.25rem;
		background: rgba(224, 90, 90, 0.15);
		color: #e05a5a;
		border: 1px solid rgba(224, 90, 90, 0.3);
		cursor: pointer;
		transition:
			background 0.15s ease,
			color 0.15s ease;
	}

	.tuner-terminate-btn:hover {
		background: #e05a5a;
		color: #fff;
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

	.tuner-status-empty {
		margin: 0;
		font-size: 0.8rem;
		color: var(--color-text-muted);
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
