<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import {
		api,
		type HDHomeRunChannel,
		type HDHomeRunGuideEntry,
		type HDHomeRunRecordingRule,
		type HDHomeRunTranscodeInfo,
		type RecordingRuleOptions,
	} from '$lib/api';
	import { findMatchingRecordingRule } from '$lib/recording-rules';
	import { parseThumbnailVtt, type CaptionCue, type ThumbnailCue } from '$lib/vtt-parser';
	import { createCaptionController } from '$lib/caption-controller';
	import { createMpegtsPlayer } from '$lib/mpegts-player';
	import HDHomeRunPlayerRecordMenu from './player/HDHomeRunPlayerRecordMenu.svelte';

	interface Props {
		src: string;
		title: string;
		playUrl?: string;
		recordingId?: string | null;
		// This viewer's own watch-session lifecycle token, used for
		// promote/heartbeat/stop - distinct from recordingId, which is the
		// shared capture identity used for stream/detail/caption URLs.
		watchSessionId?: string | null;
		startTimestamp?: number | null;
		recordEndTimestamp?: number | null;
		seekable?: boolean;
		// True when recordingId is an auto-started live-watch capture (see
		// backend/app/dvr/builtin/watch.py) rather than a genuine recordings-
		// library entry - controls whether the Record button promotes it.
		isWatchSession?: boolean;
		onClose: () => void;
		channel?: HDHomeRunChannel | null;
		airing?: HDHomeRunGuideEntry | null;
		recordingRules?: HDHomeRunRecordingRule[];
		pendingRuleIds?: Set<string>;
		officialDvrActive?: boolean;
		recordingLoading?: string | null;
		onRecordEpisode?: (
			seriesId?: string | null,
			channelNumber?: string,
			start?: number | null,
			options?: RecordingRuleOptions,
		) => Promise<void> | void;
		onRecordSeries?: (
			seriesId: string,
			channelNumber?: string,
			options?: RecordingRuleOptions,
		) => Promise<void> | void;
		onCancelRule?: (ruleId: string) => Promise<void> | void;
	}

	let {
		src,
		title,
		playUrl,
		recordingId,
		watchSessionId,
		startTimestamp,
		recordEndTimestamp,
		seekable,
		isWatchSession = false,
		onClose,
		channel = null,
		airing = null,
		recordingRules = [],
		pendingRuleIds = new Set<string>(),
		officialDvrActive = false,
		recordingLoading = null,
		onRecordEpisode,
		onRecordSeries,
		onCancelRule,
	}: Props = $props();

	const DETAIL_POLL_INTERVAL_MS = 5_000;
	const CAPTION_POLL_INTERVAL_MS = 1_000;

	let videoElement = $state<HTMLVideoElement | null>(null);
	let videoCurrentTime = $state(0);
	let baseOffsetSeconds = $state(0);
	let duration = $state<number | null>(null);
	let isInProgress = $state(false);
	let videoInfo = $state<{
		codec: string | null;
		width: number | null;
		height: number | null;
		fps: number | null;
	} | null>(null);
	let audioTracks = $state<{ index: number; codec: string | null; channels: number | null; language: string | null }[]>(
		[],
	);
	let hasCaptions = $state(false);
	let transcodeInfo = $state<HDHomeRunTranscodeInfo | null>(null);
	let currentAudioIndex = $state<number | null>(null);
	let captionsEnabled = $state(false);
	let thumbnailsAvailable = $state(false);
	let thumbnailCues: ThumbnailCue[] = [];
	let thumbSpriteUrl = $state('');

	// Captions are extracted once for the whole recording, so their cue
	// timestamps are absolute (0 = start of the recording). But each seek
	// tears down and recreates the mpegts player against a freshly
	// `-ss`-seeked ffmpeg stream, which resets the video element's own
	// currentTime back to 0 - so the native VTT cue times would only ever
	// line up with playback when baseOffsetSeconds is 0. A plain
	// `<track src>` can't be re-timed after the browser parses it, so
	// cues are parsed here and re-added to a managed TextTrack (owned by
	// captionController below), shifted by -baseOffsetSeconds, every time
	// the playback origin changes.
	let captionCues = $state<CaptionCue[]>([]);

	let showAudioMenu = $state(false);
	let showPlaybackInfo = $state(false);
	let showRecordMenu = $state(false);
	let showOptionsDialog = $state(false);
	let internalRecordingLoading = $state(false);
	let hoverPreview = $state<{ x: number; cue: ThumbnailCue } | null>(null);

	let errorMessage = $state<string | null>(null);
	let errorDetail = $state<string | null>(null);
	let destroyed = false;
	let detailPollHandle: ReturnType<typeof setInterval> | undefined;
	let captionPollHandle: ReturnType<typeof setInterval> | undefined;
	let captionsPollInFlight = false;
	let scrubBarEl: HTMLDivElement | null = $state(null);

	const effectiveAiring = $derived.by<HDHomeRunGuideEntry | null>(() => {
		if (airing) return airing;
		if (channel?.now) return channel.now;
		if (channel) {
			return {
				title: channel.name || title,
				episode_title: null,
				start: Math.floor(Date.now() / 1000),
				end: null,
				series_id: null,
				channel_number: channel.channel_number,
			};
		}
		return null;
	});

	const channelNumber = $derived(channel?.channel_number ?? effectiveAiring?.channel_number);
	const channelName = $derived(channel?.name ?? channelNumber ?? title);

	const currentRule = $derived(findMatchingRecordingRule(recordingRules, channelNumber, effectiveAiring));

	const isPending = $derived(
		currentRule !== null && pendingRuleIds.has(currentRule.RecordingRuleID),
	);

	const canRecord = $derived(
		(!seekable || isWatchSession) && (channel !== null || airing !== null || Boolean(channelNumber)),
	);

	const isActionLoading = $derived(
		internalRecordingLoading ||
			(recordingLoading !== null &&
				(currentRule
					? recordingLoading === currentRule.RecordingRuleID
					: recordingLoading === (effectiveAiring?.series_id || channelNumber || 'now'))),
	);

	async function handleRecordEpisode(options?: RecordingRuleOptions) {
		showRecordMenu = false;
		showOptionsDialog = false;
		internalRecordingLoading = true;
		try {
			if (isWatchSession && watchSessionId) {
				// Promote the auto-capture that's been running since the channel
				// was opened, so the resulting recording covers from then, not
				// from this button press.
				await api.promoteWatch(watchSessionId, {
					title: effectiveAiring?.title ?? channelName,
					episode_title: effectiveAiring?.episode_title ?? undefined,
				});
				return;
			}
			if (onRecordEpisode) {
				await onRecordEpisode(
					effectiveAiring?.series_id,
					channelNumber,
					effectiveAiring?.start,
					options,
				);
			} else {
				await api.addHDHomeRunRecordingRule({
					series_id: effectiveAiring?.series_id || 'auto',
					channel: channelNumber,
					date_time: effectiveAiring?.start ?? undefined,
					start_padding: options?.startPadding,
					end_padding: options?.endPadding,
					recent_only: options?.recentOnly,
					max_episodes_to_keep: options?.maxEpisodesToKeep,
					server: options?.server,
				});
			}
		} catch (err) {
			errorMessage = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			internalRecordingLoading = false;
		}
	}

	async function handleRecordSeries(options?: RecordingRuleOptions) {
		if (!effectiveAiring?.series_id) return;
		showRecordMenu = false;
		showOptionsDialog = false;
		internalRecordingLoading = true;
		try {
			if (isWatchSession && watchSessionId) {
				// Promote the current capture so this episode is covered from
				// channel-open time; the rule below still gets created so future
				// episodes keep getting scheduled.
				await api.promoteWatch(watchSessionId, {
					title: effectiveAiring?.title ?? channelName,
					episode_title: effectiveAiring?.episode_title ?? undefined,
				});
			}
			if (onRecordSeries) {
				await onRecordSeries(effectiveAiring.series_id, channelNumber, options);
			} else {
				await api.addHDHomeRunRecordingRule({
					series_id: effectiveAiring.series_id,
					channel: channelNumber,
					start_padding: options?.startPadding,
					end_padding: options?.endPadding,
					recent_only: options?.recentOnly,
					max_episodes_to_keep: options?.maxEpisodesToKeep,
					server: options?.server,
				});
			}
		} catch (err) {
			errorMessage = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			internalRecordingLoading = false;
		}
	}

	async function handleCancelRecording() {
		if (!currentRule) return;
		showRecordMenu = false;
		internalRecordingLoading = true;
		try {
			if (onCancelRule) {
				await onCancelRule(currentRule.RecordingRuleID);
			} else {
				await api.deleteHDHomeRunRecordingRule(currentRule.RecordingRuleID);
			}
		} catch (err) {
			errorMessage = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			internalRecordingLoading = false;
		}
	}

	function handleConfirmOptions(mode: 'episode' | 'series', options: RecordingRuleOptions) {
		if (mode === 'series') {
			handleRecordSeries(options);
		} else {
			handleRecordEpisode(options);
		}
	}

	const displayedPosition = $derived(baseOffsetSeconds + videoCurrentTime);
	const progressPercent = $derived(duration ? Math.min(100, (displayedPosition / duration) * 100) : 0);
	const captionsUrl = $derived(
		playUrl
			? api.hdhomerunRecordingCaptionsUrl({
					url: playUrl,
					recordingId: recordingId ?? '',
					recordEnd: recordEndTimestamp,
				})
			: '',
	);

	const captionController = createCaptionController({
		getVideoElement: () => videoElement,
		getCaptionsUrl: () => captionsUrl,
		getSeekable: () => seekable,
		getCaptionsEnabled: () => captionsEnabled,
		getIsInProgress: () => isInProgress,
		getDuration: () => duration,
		getVideoCurrentTime: () => videoCurrentTime,
		getCaptionCues: () => captionCues,
		setCaptionCues: (cues) => {
			captionCues = cues;
		},
		getHasCaptions: () => hasCaptions,
		setHasCaptions: (value) => {
			hasCaptions = value;
		},
		getBaseOffsetSeconds: () => baseOffsetSeconds,
		setBaseOffsetSeconds: (value) => {
			baseOffsetSeconds = value;
		},
	});

	function genericHint() {
		return get(_)('hdhomerun.detail.playback_failed_hint', {
			values: { action: get(_)('hdhomerun.detail.open_external') },
		});
	}

	const mpegtsPlayer = createMpegtsPlayer({
		getDestroyed: () => destroyed,
		setErrorMessage: (message) => {
			errorMessage = message;
		},
		setErrorDetail: (detail) => {
			errorDetail = detail;
		},
		genericHint,
	});

	function formatTime(seconds: number): string {
		if (isNaN(seconds) || seconds < 0) return '0:00';
		const m = Math.floor(seconds / 60);
		const s = Math.floor(seconds % 60);
		const h = Math.floor(m / 60);
		const remM = m % 60;
		if (h > 0) {
			return `${h}:${remM.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
		}
		return `${m}:${s.toString().padStart(2, '0')}`;
	}

	function buildStreamUrl(startSeconds: number | undefined, audioIndex: number | null): string {
		if (!seekable || !playUrl) return src;
		return api.hdhomerunRecordingStreamUrl(playUrl, {
			start: startSeconds,
			audioIndex: audioIndex ?? undefined,
			recordingId,
		});
	}

	async function loadDetail(): Promise<void> {
		if (!seekable || !playUrl) return;
		try {
			const detail = await api.hdhomerunRecordingDetail({
				url: playUrl,
				recordingId: recordingId ?? '',
				start: startTimestamp,
				recordEnd: recordEndTimestamp,
			});
			duration = detail.duration_seconds;
			isInProgress = detail.is_in_progress;
			videoInfo = detail.video;
			audioTracks = detail.audio;
			hasCaptions = detail.has_captions;
			transcodeInfo = detail.transcode;
		} catch {
			// Detail is an enhancement (duration/menus/captions) — playback
			// itself doesn't depend on it, so a failed fetch just means those
			// stay unavailable.
		}
	}

	async function loadThumbnails(): Promise<void> {
		if (!seekable || !playUrl || isInProgress) return;
		try {
			const vttUrl = api.hdhomerunRecordingThumbnailVttUrl({
				url: playUrl,
				recordingId: recordingId ?? '',
				recordEnd: recordEndTimestamp,
			});
			const response = await fetch(vttUrl, { credentials: 'include' });
			if (!response.ok) return;
			const text = await response.text();
			const cues = parseThumbnailVtt(text);
			if (cues.length === 0) return;
			thumbnailCues = cues;
			thumbSpriteUrl = api.hdhomerunRecordingThumbnailSpriteUrl({
				url: playUrl,
				recordingId: recordingId ?? '',
				recordEnd: recordEndTimestamp,
			});
			thumbnailsAvailable = true;
		} catch {
			// No thumbnails: hover preview stays off, scrub bar still works.
		}
	}

	const activeCaptionLines = $derived.by<string[]>(() => {
		if (!captionsEnabled || captionCues.length === 0) return [];
		const pos = displayedPosition;
		const active = captionCues.filter((cue) => {
			const start = cue.displayStart ?? cue.start;
			const end = cue.displayEnd ?? cue.end;
			return pos >= start && pos <= end;
		});
		if (active.length === 0) return [];
		const lines: string[] = [];
		for (const cue of active) {
			for (const line of cue.text.split('\n')) {
				if (line.length > 0) lines.push(line);
			}
		}
		return lines;
	});

	function findCueAt(seconds: number): ThumbnailCue | null {
		if (thumbnailCues.length === 0) return null;
		let found = thumbnailCues[0];
		for (const cue of thumbnailCues) {
			if (cue.startSeconds > seconds) break;
			found = cue;
		}
		return found;
	}

	function stopPolling() {
		if (detailPollHandle !== undefined) {
			clearInterval(detailPollHandle);
			detailPollHandle = undefined;
		}
	}

	function startPolling() {
		if (detailPollHandle !== undefined) return;
		detailPollHandle = setInterval(async () => {
			const wasInProgress = isInProgress;
			await loadDetail();
			captionController.maybeResyncBaseOffset();
			if (wasInProgress && !isInProgress) {
				stopPolling();
				stopCaptionPolling();
				loadThumbnails();
				captionController.loadCaptions();
			}
		}, DETAIL_POLL_INTERVAL_MS);
	}

	function stopCaptionPolling() {
		if (captionPollHandle !== undefined) {
			clearInterval(captionPollHandle);
			captionPollHandle = undefined;
		}
	}

	function startCaptionPolling() {
		if (captionPollHandle !== undefined) return;
		captionPollHandle = setInterval(async () => {
			if (!isInProgress) {
				stopCaptionPolling();
				return;
			}
			if (captionsPollInFlight) return;
			captionsPollInFlight = true;
			try {
				await captionController.pollLiveCaptions();
			} finally {
				captionsPollInFlight = false;
			}
		}, CAPTION_POLL_INTERVAL_MS);
	}

	function seekTo(targetSeconds: number) {
		if (!seekable || !videoElement) return;
		let clamped = Math.max(0, targetSeconds);
		if (duration !== null) clamped = Math.min(clamped, duration);
		mpegtsPlayer.teardownPlayer();
		baseOffsetSeconds = clamped;
		videoCurrentTime = 0;
		captionController.resetStretchCursor();
		captionController.refreshCaptionCues();
		mpegtsPlayer.createPlayerAt(videoElement, buildStreamUrl(clamped, currentAudioIndex));
	}

	function rewind(seconds = 10) {
		if (seekable) {
			seekTo(displayedPosition - seconds);
		} else if (videoElement) {
			videoElement.currentTime = Math.max(0, videoElement.currentTime - seconds);
		}
	}

	function fastForward(seconds = 10) {
		if (seekable) {
			seekTo(displayedPosition + seconds);
		} else if (videoElement) {
			videoElement.currentTime = videoElement.currentTime + seconds;
		}
	}

	function safePlay() {
		if (!videoElement) return;
		try {
			const res = videoElement.play();
			if (res && typeof res.catch === 'function') res.catch(() => {});
		} catch {
			// ignore play errors in non-media environments
		}
	}

	function togglePlay() {
		if (!videoElement) return;
		if (videoElement.paused) {
			safePlay();
		} else {
			videoElement.pause();
		}
	}

	function toggleCaptions() {
		captionsEnabled = !captionsEnabled;
		captionController.ensureCaptionTrack();
	}

	function selectAudioTrack(index: number) {
		if (!seekable || index === currentAudioIndex) return;
		currentAudioIndex = index;
		showAudioMenu = false;
		seekTo(displayedPosition);
	}

	function handleScrubClick(e: MouseEvent) {
		if (!seekable || duration === null || !scrubBarEl) return;
		const rect = scrubBarEl.getBoundingClientRect();
		const fraction = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
		seekTo(fraction * duration);
	}

	function handleScrubHover(e: MouseEvent) {
		if (!seekable || duration === null || !scrubBarEl || !thumbnailsAvailable) return;
		const rect = scrubBarEl.getBoundingClientRect();
		const fraction = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
		const cue = findCueAt(fraction * duration);
		if (cue) hoverPreview = { x: e.clientX - rect.left, cue };
	}

	function handleScrubKeydown(e: KeyboardEvent) {
		if (!seekable || duration === null) return;
		if (e.key === 'ArrowLeft') {
			e.preventDefault();
			seekTo(Math.max(0, displayedPosition - 10));
		} else if (e.key === 'ArrowRight') {
			e.preventDefault();
			seekTo(Math.min(duration, displayedPosition + 10));
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			if (showPlaybackInfo) {
				showPlaybackInfo = false;
			} else if (showAudioMenu) {
				showAudioMenu = false;
			} else if (showRecordMenu) {
				showRecordMenu = false;
			} else if (showOptionsDialog) {
				showOptionsDialog = false;
			} else {
				onClose();
			}
		} else if (e.key === ' ') {
			e.preventDefault();
			togglePlay();
		} else if (e.key === 'ArrowLeft' || e.key === 'j') {
			rewind(10);
		} else if (e.key === 'ArrowRight' || e.key === 'l') {
			fastForward(10);
		} else if (e.key === 'c' && hasCaptions) {
			toggleCaptions();
		} else if (e.key === 'r' && canRecord) {
			showRecordMenu = !showRecordMenu;
		}
	}

	// See JellyfinPlayer.svelte for why this overlay is portaled to <body>.
	function portal(node: HTMLElement) {
		document.body.appendChild(node);
		return {
			destroy() {
				node.remove();
			},
		};
	}

	function attachPlayer(node: HTMLVideoElement) {
		videoElement = node;

		(async () => {
			if (seekable) {
				await loadDetail();
				if (destroyed) return;
				if (isInProgress) {
					baseOffsetSeconds = duration ?? 0;
					mpegtsPlayer.createPlayerAt(node, buildStreamUrl(undefined, currentAudioIndex));
					captionController.pollLiveCaptions();
					startPolling();
					startCaptionPolling();
				} else {
					baseOffsetSeconds = 0;
					mpegtsPlayer.createPlayerAt(node, buildStreamUrl(0, currentAudioIndex));
					loadThumbnails();
					captionController.loadCaptions();
				}
			} else {
				mpegtsPlayer.createPlayerAt(node, src);
			}
		})();

		return {
			destroy() {
				// Closes the underlying HTTP connection — this is what lets the
				// backend's stream route notice the disconnect and kill its
				// ffmpeg process. Skipping this leaks it indefinitely.
				destroyed = true;
				stopPolling();
				stopCaptionPolling();
				mpegtsPlayer.teardownPlayer();
				videoElement = null;
				captionController.teardown();
				captionCues = [];
			},
		};
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="overlay" role="dialog" aria-label={title} use:portal>
	<div class="header">
		<h2>{title}</h2>
		<div class="controls">
			{#if canRecord}
				<HDHomeRunPlayerRecordMenu
					{currentRule}
					{isPending}
					{isActionLoading}
					{channelName}
					{effectiveAiring}
					{officialDvrActive}
					bind:showRecordMenu
					bind:showOptionsDialog
					onRecordEpisode={handleRecordEpisode}
					onRecordSeries={handleRecordSeries}
					onCancelRecording={handleCancelRecording}
					onConfirmOptions={handleConfirmOptions}
				/>
			{/if}
			{#if seekable && (videoInfo || audioTracks.length > 0 || transcodeInfo)}
				<button
					class="control-btn"
					class:active={showPlaybackInfo}
					onclick={() => (showPlaybackInfo = !showPlaybackInfo)}
					aria-label={$_('player.playback_info')}
					title={$_('player.playback_info')}
				>
					ℹ
				</button>
			{/if}
			{#if seekable && hasCaptions}
				<button
					class="control-btn"
					class:active={captionsEnabled}
					onclick={toggleCaptions}
					aria-label={$_('player.subtitles')}
					title={$_('player.subtitles')}
				>
					💬 CC
				</button>
			{/if}
			{#if seekable && audioTracks.length > 1}
				<div class="menu-popover-wrap">
					<button
						class="control-btn"
						class:active={showAudioMenu}
						onclick={() => (showAudioMenu = !showAudioMenu)}
						aria-label={$_('player.audio_tracks')}
					>
						🔊 {$_('player.audio_tracks')}
					</button>
					{#if showAudioMenu}
						<div class="popover-menu">
							<div class="menu-header">{$_('player.audio_tracks')}</div>
							<div class="menu-items">
								{#each audioTracks as track (track.index)}
									<button
										class="menu-item"
										class:selected={currentAudioIndex === track.index ||
											(currentAudioIndex === null && track.index === 0)}
										onclick={() => selectAudioTrack(track.index)}
									>
										{track.language ? track.language.toUpperCase() : `Track ${track.index + 1}`}
										{#if track.channels}({track.channels}ch){/if}
									</button>
								{/each}
							</div>
						</div>
					{/if}
				</div>
			{/if}
			<button class="control-btn" onclick={() => rewind(10)} aria-label={$_('player.rewind')}>↺ 10s</button>
			<button class="control-btn" onclick={() => fastForward(10)} aria-label={$_('player.fast_forward')}>↻ 10s</button>
			<button class="close" onclick={onClose} aria-label={$_('player.close')}>✕</button>
		</div>
	</div>
	{#if errorMessage}
		<p class="error">
			{errorMessage}
			{#if errorDetail}
				<span class="error-detail">{errorDetail}</span>
			{/if}
		</p>
	{/if}

	<div class="video-container">
		<!-- svelte-ignore a11y_media_has_caption -->
		<video
			autoplay
			playsinline
			controls={!seekable}
			class="video"
			use:attachPlayer
			bind:currentTime={videoCurrentTime}
			crossorigin="use-credentials"
		></video>

		{#if captionsEnabled && activeCaptionLines.length > 0}
			<div class="caption-overlay" class:with-scrub={seekable} aria-live="polite">
				{#each activeCaptionLines as line, i (i + line)}
					<div class="caption-line">{line}</div>
				{/each}
			</div>
		{/if}

		{#if seekable}
			<div class="scrub-container">
				<div class="scrub-time">{formatTime(displayedPosition)}</div>
				<div
					class="scrub-bar"
					class:disabled={duration === null}
					bind:this={scrubBarEl}
					onclick={handleScrubClick}
					onmousemove={handleScrubHover}
					onmouseleave={() => (hoverPreview = null)}
					onkeydown={handleScrubKeydown}
					role="slider"
					aria-label={$_('player.playback_info')}
					aria-valuemin="0"
					aria-valuemax={duration ?? 0}
					aria-valuenow={displayedPosition}
					tabindex="0"
				>
					<div class="scrub-track">
						<div class="scrub-fill" style:width="{progressPercent}%"></div>
					</div>
					{#if hoverPreview}
						<div
							class="thumb-preview"
							style:left="{hoverPreview.x}px"
							style:width="{hoverPreview.cue.w}px"
							style:height="{hoverPreview.cue.h}px"
							style:background-image="url({thumbSpriteUrl})"
							style:background-position="-{hoverPreview.cue.x}px -{hoverPreview.cue.y}px"
						>
							<span class="thumb-time">{formatTime(hoverPreview.cue.startSeconds)}</span>
						</div>
					{/if}
				</div>
				<div class="scrub-time">
					{isInProgress ? $_('hdhomerun.detail.recording_in_progress') : formatTime(duration ?? 0)}
				</div>
			</div>
		{/if}
	</div>

	{#if showPlaybackInfo && seekable}
		<div class="info-overlay-modal" role="dialog" aria-label={$_('player.playback_info')}>
			<div class="info-card">
				<div class="info-header">
					<h3>{$_('player.playback_info')}</h3>
					<button class="info-close" onclick={() => (showPlaybackInfo = false)}>✕</button>
				</div>
				<div class="info-body">
					<div class="info-row">
						<span class="label">{$_('player.container')}:</span>
						<span class="value uppercase">MPEG-TS</span>
					</div>
					{#if transcodeInfo}
						<div class="info-row">
							<span class="label">{$_('player.transcoding')}:</span>
							<span class="value">
								{#if transcodeInfo.transcoding}
									{$_('player.transcoding_via', { values: { preset: transcodeInfo.preset_label } })}
									{#if transcodeInfo.hardware}<span class="hw-badge">HW</span>{/if}
								{:else}
									{$_('player.direct_passthrough')}
								{/if}
							</span>
						</div>
					{/if}
					{#if isInProgress && !videoInfo && audioTracks.length === 0}
						<div class="info-row">
							<span class="value">{$_('player.analyzing_stream')}</span>
						</div>
					{/if}
					{#if videoInfo}
						<div class="info-section-heading">{$_('player.video')}</div>
						<div class="info-row">
							<span class="label">Codec:</span>
							<span class="value uppercase">{videoInfo.codec ?? $_('common.unknown')}</span>
						</div>
						{#if videoInfo.width && videoInfo.height}
							<div class="info-row">
								<span class="label">{$_('player.resolution')}:</span>
								<span class="value">{videoInfo.width}×{videoInfo.height}</span>
							</div>
						{/if}
						{#if videoInfo.fps}
							<div class="info-row">
								<span class="label">Framerate:</span>
								<span class="value">{videoInfo.fps} fps</span>
							</div>
						{/if}
					{/if}
					{#if audioTracks.length > 0}
						<div class="info-section-heading">{$_('player.audio')}</div>
						{#each audioTracks as track (track.index)}
							<div class="info-row">
								<span class="label">Track {track.index + 1}:</span>
								<span class="value uppercase">{track.codec ?? $_('common.unknown')} · {track.channels ?? '?'}ch</span>
							</div>
						{/each}
					{/if}
					<div class="info-row">
						<span class="label">{$_('player.duration')}:</span>
						<span class="value">{duration !== null ? formatTime(duration) : $_('common.unknown')}</span>
					</div>
				</div>
			</div>
		</div>
	{/if}

</div>

<style>
	.overlay {
		position: fixed;
		inset: 0;
		z-index: 100;
		background: #000;
		display: flex;
		flex-direction: column;
	}

	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.75rem 1rem;
		background: rgba(0, 0, 0, 0.6);
	}

	.header h2 {
		margin: 0;
		color: #fff;
		font-size: 1rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.controls {
		display: flex;
		align-items: center;
		gap: 0.5rem;
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

	.close {
		flex-shrink: 0;
		background: none;
		border: 1px solid rgba(255, 255, 255, 0.4);
		border-radius: 50%;
		width: 2rem;
		height: 2rem;
		color: #fff;
		cursor: pointer;
	}

	.error {
		margin: 0;
		padding: 0.75rem 1rem;
		color: #ffb4b4;
		background: rgba(224, 90, 90, 0.15);
	}

	.error-detail {
		display: block;
		margin-top: 0.35rem;
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 0.75rem;
		max-height: 6rem;
		overflow: auto;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		opacity: 0.85;
	}

	.video-container {
		position: relative;
		flex: 1;
		display: flex;
		flex-direction: column;
		min-height: 0;
		background: #000;
	}

	.video {
		flex: 1;
		width: 100%;
		min-height: 0;
		object-fit: contain;
		background: #000;
	}

	.caption-overlay {
		position: absolute;
		bottom: 1.5rem;
		left: 50%;
		transform: translateX(-50%);
		max-width: 85%;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		pointer-events: none;
		z-index: 10;
		text-align: center;
	}

	.caption-overlay.with-scrub {
		bottom: 4rem;
	}

	.caption-line {
		display: inline-block;
		background: rgba(0, 0, 0, 0.82);
		color: #ffffff;
		padding: 0.25rem 0.6rem;
		border-radius: 0.25rem;
		font-size: 1.1rem;
		line-height: 1.4;
		font-weight: 500;
		text-shadow: 0 1px 2px rgba(0, 0, 0, 0.9);
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
		white-space: pre-wrap;
		word-break: break-word;
	}

	.scrub-container {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.5rem 1rem;
		background: rgba(0, 0, 0, 0.85);
		border-top: 1px solid rgba(255, 255, 255, 0.1);
	}

	.scrub-time {
		color: rgba(255, 255, 255, 0.75);
		font-size: 0.8rem;
		font-family: ui-monospace, SFMono-Regular, monospace;
		white-space: nowrap;
	}

	.scrub-bar {
		position: relative;
		flex: 1;
		cursor: pointer;
		padding: 0.5rem 0;
	}

	.scrub-bar.disabled {
		cursor: default;
		opacity: 0.5;
		pointer-events: none;
	}

	.scrub-track {
		position: relative;
		height: 0.35rem;
		border-radius: 0.2rem;
		background: rgba(255, 255, 255, 0.2);
		overflow: hidden;
	}

	.scrub-fill {
		height: 100%;
		background: #38bdf8;
	}

	.thumb-preview {
		position: absolute;
		bottom: 100%;
		margin-bottom: 0.5rem;
		transform: translateX(-50%);
		border: 2px solid rgba(255, 255, 255, 0.9);
		border-radius: 0.3rem;
		background-repeat: no-repeat;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6);
		display: flex;
		align-items: flex-end;
		justify-content: center;
	}

	.thumb-time {
		background: rgba(0, 0, 0, 0.75);
		color: #fff;
		font-size: 0.65rem;
		padding: 0.05rem 0.25rem;
		border-radius: 0.2rem;
		margin: 0.2rem;
	}

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

	.menu-item.selected {
		color: #38bdf8;
		font-weight: 600;
		background: rgba(56, 189, 248, 0.15);
	}

	.info-overlay-modal {
		position: absolute;
		inset: 0;
		z-index: 150;
		background: rgba(0, 0, 0, 0.65);
		backdrop-filter: blur(6px);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.info-card {
		background: rgba(30, 30, 35, 0.95);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.75rem;
		width: 100%;
		max-width: 24rem;
		padding: 1.25rem;
		color: #fff;
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.7);
	}

	.info-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 1rem;
	}

	.info-header h3 {
		margin: 0;
		font-size: 1.1rem;
	}

	.info-close {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.6);
		font-size: 1.1rem;
		cursor: pointer;
	}

	.info-body {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		font-size: 0.9rem;
	}

	.info-section-heading {
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		color: #38bdf8;
		margin-top: 0.6rem;
		margin-bottom: 0.2rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		padding-bottom: 0.2rem;
	}

	.info-row {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
	}

	.info-row .label {
		color: rgba(255, 255, 255, 0.6);
	}

	.info-row .value {
		font-weight: 500;
		text-align: right;
	}

	.uppercase {
		text-transform: uppercase;
	}

	.hw-badge {
		display: inline-block;
		margin-left: 0.4rem;
		padding: 0.05rem 0.35rem;
		font-size: 0.65rem;
		font-weight: 700;
		border-radius: 3px;
		background: rgba(56, 189, 248, 0.2);
		color: #38bdf8;
	}

</style>
