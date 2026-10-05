<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import {
		api,
		type CommercialSegment,
		type HDHomeRunChannel,
		type HDHomeRunGuideEntry,
		type HDHomeRunRecordingAudioInfo,
		type HDHomeRunRecordingRule,
		type HDHomeRunTranscodeInfo,
		type RecordingRuleOptions,
		type SyncPlayContent,
		type SyncPlayRoom,
	} from '$lib/api';
	import { findMatchingRecordingRule } from '$lib/recording-rules';
	import { parseThumbnailVtt, type CaptionCue, type ThumbnailCue } from '$lib/vtt-parser';
	import { createCaptionController } from '$lib/caption-controller';
	import { createMpegtsPlayer } from '$lib/mpegts-player';
	import { createSyncPlayController, type SyncPlayStatus } from '$lib/syncplay-controller';
	import { createAirPlayController } from '$lib/airplay-controller';
	import { createRecordingActionsController } from '$lib/recording-actions';
	import { getQualityPreference, setQualityPreference, type QualityPreference } from '$lib/quality-preference';
	import { autoSkipCommercials } from '$lib/stores/playback';
	import PlayerHeader from './player/PlayerHeader.svelte';
	import PlayerFooter from './player/PlayerFooter.svelte';
	import PlayerIcon from './player/icons/PlayerIcon.svelte';
	import LoadingQuipOverlay from './player/LoadingQuipOverlay.svelte';
	import SyncPlayModal from './player/SyncPlayModal.svelte';
	import PlayerChannelDrawer from './player/PlayerChannelDrawer.svelte';
	import MiniPlayer from './player/MiniPlayer.svelte';
	import { openPopoutPlayer } from '$lib/popout';

	interface Props {
		src: string;
		title: string;
		playUrl?: string;
		recordingId?: string | null;
		watchSessionId?: string | null;
		startTimestamp?: number | null;
		recordEndTimestamp?: number | null;
		seekable?: boolean;
		isWatchSession?: boolean;
		onClose: () => void;
		channel?: HDHomeRunChannel | null;
		airing?: HDHomeRunGuideEntry | null;
		channels?: HDHomeRunChannel[];
		favoriteChannels?: Set<string>;
		recordingRules?: HDHomeRunRecordingRule[];
		pendingRuleIds?: Set<string>;
		officialDvrActive?: boolean;
		recordingLoading?: string | null;
		onRecordEpisode?: (
			seriesId?: string | null,
			channelNumber?: string | null,
			start?: number | null,
			options?: RecordingRuleOptions,
		) => Promise<void> | void;
		onRecordSeries?: (
			seriesId: string,
			channelNumber?: string | null,
			options?: RecordingRuleOptions,
		) => Promise<void> | void;
		onUpdateRule?: (
			ruleId: string,
			mode: 'episode' | 'series',
			options: RecordingRuleOptions,
		) => Promise<void> | void;
		onCancelRule?: (ruleId: string) => Promise<void> | void;
		onToggleFavorite?: (channelNumber: string) => Promise<void> | void;
		onChannelChange?: (channel: HDHomeRunChannel) => void;
		onToggleMultiView?: () => void;
		allowPopout?: boolean;
		onPopout?: () => void;
		displayMode?: 'full' | 'mini';
		onExpand?: () => void;
	}

	let {
		src,
		title,
		playUrl,
		recordingId,
		watchSessionId,
		startTimestamp,
		recordEndTimestamp,
		seekable = false,
		isWatchSession = false,
		onClose,
		channel = null,
		airing = null,
		channels = [],
		favoriteChannels = new Set<string>(),
		recordingRules = [],
		pendingRuleIds = new Set<string>(),
		officialDvrActive = false,
		recordingLoading = null,
		allowPopout = true,
		onPopout,
		displayMode = 'full',
		onExpand,
		onRecordEpisode,
		onRecordSeries,
		onUpdateRule,
		onCancelRule,
		onToggleFavorite,
		onChannelChange,
		onToggleMultiView,
	}: Props = $props();

	const DETAIL_POLL_INTERVAL_MS = 5_000;
	const CAPTION_POLL_INTERVAL_MS = 500;

	let overlayEl = $state<HTMLDivElement | null>(null);
	let videoElement = $state<HTMLVideoElement | null>(null);
	let videoCurrentTime = $state(0);
	let baseOffsetSeconds = $state(0);
	let duration = $state<number | null>(null);
	let isInProgress = $state(false);
	let videoPaused = $state(false);
	let isFullscreen = $state(false);
	let pipSupported = $state(false);
	let isPipActive = $state(false);
	let volume = $state(1.0);
	let muted = $state(false);
	let playbackRate = $state(1.0);
	let aspectRatio = $state<'contain' | 'cover' | 'fill' | '16:9' | '4:3'>('contain');
	// The tiers "auto" mode can resolve to - a superset of the manually
	// selectable ones (QualityPreference), with "minimal" as a floor below
	// "low" that's never offered in the picker (see QUALITY_TIERS in
	// backend/app/transcoding.py) but that auto-downgrade can still reach on
	// a connection too slow even for "low".
	type AutoTier = 'high' | 'medium' | 'low' | 'minimal';

	// User-facing preference (persisted). When this is "auto", the tier
	// actually requested from the backend is autoEffectiveTier below, which
	// can step down on its own as the network struggles.
	let quality = $state<QualityPreference>('auto');
	let autoEffectiveTier = $state<AutoTier>('high');
	// Rolling window of recent stalls, used to auto-downgrade quality on a
	// struggling network - see recordStallAndMaybeDowngrade(). Only consulted
	// while quality is "auto"; a manual tier choice is never overridden.
	let stallTimestamps: number[] = [];
	// Recent measured download-speed samples (Mbps), used for the proactive
	// half of auto quality adjustment - see sampleThroughput(). Most recent
	// last; trimmed to UPGRADE_WINDOW_SAMPLES.
	let speedSamplesMbps: number[] = [];
	// Last sample, kept as its own $state purely for the Playback Info
	// overlay - speedSamplesMbps itself isn't reactive (mutated in place by
	// sampleThroughput's polling interval, not through Svelte's reactivity).
	let measuredSpeedMbps = $state<number | null>(null);
	// What the auto-adjust logic last did and why, shown in the Playback
	// Info overlay so a downgrade/upgrade is actually visible to the viewer,
	// not just inferred from the transient notice toast.
	let lastQualityAdjustment = $state<{
		direction: 'down' | 'up';
		tier: AutoTier;
		reason: 'stalling' | 'throughput' | 'recovered';
		at: number;
	} | null>(null);

	let videoInfo = $state<{
		codec: string | null;
		width: number | null;
		height: number | null;
		fps: number | null;
	} | null>(null);

	// The real decoded stream's stats - as opposed to videoInfo above, which
	// is ffprobe's read of the *source* recording/tuner file and never
	// changes when a quality tier switch changes what's actually being sent.
	// Polled from mpegts.js's mediaInfo getter (see getMediaInfo() in
	// mpegts-player.ts) for the Playback Info "stats for nerds" panel.
	let actualMediaInfo = $state<{
		codec: string | null;
		width: number | null;
		height: number | null;
		fps: number | null;
		audioCodec: string | null;
	} | null>(null);
	let decodedFrames = $state<number | null>(null);
	let droppedFrames = $state<number | null>(null);
	let audioTracks = $state<HDHomeRunRecordingAudioInfo[]>([]);
	let hasCaptions = $state(false);
	let secondaryCaptions = $state<'unknown' | 'available' | 'unavailable' | null>(null);
	let currentCaptionTrack = $state<1 | 2>(1);
	let currentAudioIndex = $state<number | null>(null);
	let captionsEnabled = $state(false);
	let thumbnailsAvailable = $state(false);
	let thumbnailCues = $state<ThumbnailCue[]>([]);
	let thumbSpriteUrl = $state('');
	let commercialSegments = $state<CommercialSegment[]>([]);
	// Tracks the start_seconds of the last segment auto-skipped, so the
	// auto-skip effect fires at most once per segment instead of re-seeking
	// on every reactive tick while still inside it.
	let lastAutoSkippedSegmentStart = $state<number | null>(null);

	let captionCues = $state<CaptionCue[]>([]);
	let transcodeInfo = $state<HDHomeRunTranscodeInfo | null>(null);

	// Menus & Modals
	let showControls = $state(true);
	let autoHideTimer: ReturnType<typeof setTimeout> | undefined;
	let showAudioMenu = $state(false);
	let showSettingsMenu = $state(false);
	let showPlaybackInfo = $state(false);
	let showRecordMenu = $state(false);
	let showOptionsDialog = $state(false);
	let showSyncPlayModal = $state(false);
	let showChannelDrawer = $state(false);
	let syncPlayRoom = $state<SyncPlayRoom | null>(null);
	let syncPlayStatus = $state<SyncPlayStatus>('disconnected');
	let syncPlayPingMs = $state(0);

	let centerFlash = $state<'play' | 'pause' | null>(null);
	let centerFlashTimer: ReturnType<typeof setTimeout> | undefined;

	// Shown briefly after joining a live/in-progress program at the live
	// edge, so a viewer who actually wanted the beginning can switch with one
	// tap instead of facing a blocking "which do you want?" dialog up front.
	let showStartOver = $state(false);
	let startOverTimer: ReturnType<typeof setTimeout> | undefined;

	// Non-blocking "Reduced quality..." style notices (auto-downgrade, etc).
	let playbackNotice = $state<string | null>(null);
	let playbackNoticeTimer: ReturnType<typeof setTimeout> | undefined;

	// Brief "Commercial skipped" pill shown in the manual button's slot when
	// a segment is auto-skipped.
	let showAutoSkipPill = $state(false);
	let autoSkipPillTimer: ReturnType<typeof setTimeout> | undefined;

	let internalRecordingLoading = $state(false);
	let isVideoLoading = $state(true);
	let errorMessage = $state<string | null>(null);
	let errorDetail = $state<string | null>(null);
	let destroyed = false;
	let detailPollHandle: ReturnType<typeof setInterval> | undefined;
	let captionPollHandle: ReturnType<typeof setInterval> | undefined;
	let throughputPollHandle: ReturnType<typeof setInterval> | undefined;
	let captionsPollInFlight = false;
	let airplayAvailable = $state(false);

	// Load stored volume settings
	if (typeof localStorage !== 'undefined') {
		try {
			const savedVol = localStorage.getItem('hdhr_player_volume');
			if (savedVol !== null) volume = Math.max(0, Math.min(1, Number(savedVol)));
			const savedMuted = localStorage.getItem('hdhr_player_muted');
			if (savedMuted !== null) muted = savedMuted === 'true';
		} catch {
			// ignore localStorage errors
		}
	}
	quality = getQualityPreference();

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
	const episodeSubtitle = $derived(effectiveAiring?.episode_title ?? undefined);

	const currentRule = $derived(findMatchingRecordingRule(recordingRules, channelNumber, effectiveAiring));

	const isPending = $derived(
		currentRule !== null && pendingRuleIds.has(currentRule.RecordingRuleID),
	);

	const canRecord = $derived(
		(!seekable || isWatchSession) && (channel !== null || airing !== null || Boolean(channelNumber)),
	);

	const isLive = $derived(isWatchSession || isInProgress || !seekable || channel !== null);

	const channelSwitcherAvailable = $derived(isLive && channels.length > 0);

	const isFavorited = $derived(
		Boolean(channelNumber && favoriteChannels.has(channelNumber)),
	);

	const isActionLoading = $derived(
		internalRecordingLoading ||
			(recordingLoading !== null &&
				(currentRule
					? recordingLoading === currentRule.RecordingRuleID
					: Boolean(
							recordingLoading &&
								(recordingLoading === effectiveAiring?.series_id ||
									recordingLoading === channelNumber ||
									recordingLoading === effectiveAiring?.title ||
									recordingLoading === 'now' ||
									recordingLoading === 'series' ||
									recordingLoading === 'auto'),
						))),
	);

	const displayedPosition = $derived(baseOffsetSeconds + videoCurrentTime);

	const activeCommercialSegment = $derived.by<CommercialSegment | null>(() => {
		for (const segment of commercialSegments) {
			if (displayedPosition >= segment.start_seconds && displayedPosition < segment.end_seconds) {
				return segment;
			}
		}
		return null;
	});

	$effect(() => {
		if (!$autoSkipCommercials) return;
		const segment = activeCommercialSegment;
		if (!segment || lastAutoSkippedSegmentStart === segment.start_seconds) return;
		lastAutoSkippedSegmentStart = segment.start_seconds;
		skipCommercial();
		showAutoSkipPill = true;
		if (autoSkipPillTimer) clearTimeout(autoSkipPillTimer);
		autoSkipPillTimer = setTimeout(() => {
			showAutoSkipPill = false;
		}, 1500);
	});

	const captionsUrl = $derived(
		playUrl
			? api.hdhomerunRecordingCaptionsUrl({
					url: playUrl,
					recordingId: recordingId ?? '',
					recordEnd: recordEndTimestamp,
					track: currentCaptionTrack,
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

	function formatAgo(seconds: number): string {
		if (seconds < 60) return `${Math.max(0, Math.round(seconds))}s`;
		const minutes = Math.round(seconds / 60);
		return `${minutes}m`;
	}

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

	function buildStreamUrl(startSeconds?: number, audioIndex: number | null = currentAudioIndex): string {
		if (!seekable || !playUrl) return src;
		const effectiveTier = quality === 'auto' ? autoEffectiveTier : quality;
		return api.hdhomerunRecordingStreamUrl(playUrl, {
			start: startSeconds,
			audioIndex: audioIndex ?? undefined,
			recordingId,
			quality: effectiveTier === 'high' ? undefined : effectiveTier,
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
			if (currentAudioIndex === null && detail.audio.length > 0) {
				currentAudioIndex = 0;
			}
			hasCaptions = detail.has_captions;
			secondaryCaptions = detail.secondary_captions;
			transcodeInfo = detail.transcode;
			// Not reset here: loadDetail() also runs on every periodic poll of
			// the SAME recording (see startPolling()), and resetting on each
			// poll would let a refined/updated segment list re-trigger a skip
			// already performed for this segment. switchMedia() (genuinely new
			// recording/channel) and the initial `$state(null)` default are
			// the only points that should clear it.
			commercialSegments = detail.commercial_segments ?? [];
		} catch {
			// Detail is an enhancement
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
			// No thumbnails: hover preview stays off
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

	function stopThroughputPolling() {
		if (throughputPollHandle !== undefined) {
			clearInterval(throughputPollHandle);
			throughputPollHandle = undefined;
		}
	}

	function startThroughputPolling() {
		if (throughputPollHandle !== undefined) return;
		throughputPollHandle = setInterval(() => {
			sampleActualMediaInfo();
			sampleThroughput();
		}, THROUGHPUT_SAMPLE_INTERVAL_MS);
	}

	// Always runs (regardless of manual/auto quality), unlike sampleThroughput -
	// this is purely informational for the Playback Info panel, not an input
	// to the auto-adjustment logic.
	function sampleActualMediaInfo() {
		const info = mpegtsPlayer.getMediaInfo();
		if (info && (info.width || info.height || info.videoCodec)) {
			actualMediaInfo = {
				codec: info.videoCodec ?? null,
				width: info.width ?? null,
				height: info.height ?? null,
				fps: info.fps ?? null,
				audioCodec: info.audioCodec ?? null,
			};
		}
		const stats = mpegtsPlayer.getStatisticsInfo();
		if (typeof stats?.decodedFrames === 'number') decodedFrames = stats.decodedFrames;
		if (typeof stats?.droppedFrames === 'number') droppedFrames = stats.droppedFrames;
	}

	function seekTo(targetSeconds: number) {
		if (!seekable || !videoElement) return;
		dismissStartOverHint();
		let clamped = Math.max(0, targetSeconds);
		if (duration !== null) clamped = Math.min(clamped, duration);
		isVideoLoading = true;
		mpegtsPlayer.teardownPlayer();
		baseOffsetSeconds = clamped;
		videoCurrentTime = 0;
		captionController.resetStretchCursor();
		captionController.refreshCaptionCues();
		mpegtsPlayer.createPlayerAt(videoElement, buildStreamUrl(clamped, currentAudioIndex));
		syncPlayController.sendSeek(clamped);
		resetAutoHideTimer();
	}

	function skipCommercial() {
		if (!activeCommercialSegment) return;
		seekTo(activeCommercialSegment.end_seconds);
	}

	const currentSyncContent = $derived.by<SyncPlayContent>(() => {
		if (channelNumber) {
			return {
				type: 'channel',
				id: channelNumber,
				title: channelName || title,
				channel_number: channelNumber,
				play_url: playUrl || undefined,
			};
		}
		return {
			type: 'recording',
			id: recordingId || 'recording',
			title: title,
			play_url: playUrl || undefined,
		};
	});

	const syncPlayController = createSyncPlayController({
		getVideoElement: () => videoElement,
		getLocalCurrentTime: () => displayedPosition,
		getIsPaused: () => videoPaused,
		onRemotePlay: (position, rate) => {
			if (videoElement) {
				if (seekable && Math.abs(displayedPosition - position) > 1.5) {
					seekTo(position);
				}
				videoElement.playbackRate = rate || 1.0;
				if (videoElement.paused) {
					safePlay();
					videoPaused = false;
					triggerCenterFlash('play');
				}
			}
		},
		onRemotePause: (position) => {
			if (videoElement) {
				if (seekable && Math.abs(displayedPosition - position) > 1.5) {
					seekTo(position);
				}
				if (!videoElement.paused) {
					videoElement.pause();
					videoPaused = true;
					triggerCenterFlash('pause');
				}
			}
		},
		onRemoteSeek: (position) => {
			if (seekable) {
				seekTo(position);
			}
		},
		onRemoteContentChange: () => {},
		onRoomStateChange: (updatedRoom) => {
			syncPlayRoom = updatedRoom;
			syncPlayStatus = syncPlayController.getStatus();
			syncPlayPingMs = syncPlayController.getPingMs();
		},
	});

	function rewind(seconds = 10) {
		if (seekable) {
			seekTo(displayedPosition - seconds);
		} else if (videoElement) {
			videoElement.currentTime = Math.max(0, videoElement.currentTime - seconds);
		}
		resetAutoHideTimer();
	}

	function fastForward(seconds = 10) {
		if (seekable) {
			seekTo(displayedPosition + seconds);
		} else if (videoElement) {
			videoElement.currentTime = videoElement.currentTime + seconds;
		}
		resetAutoHideTimer();
	}

	function safePlay() {
		if (!videoElement) return;
		try {
			const res = videoElement.play();
			if (res && typeof res.catch === 'function') res.catch(() => {});
		} catch {
			// ignore
		}
	}

	function triggerCenterFlash(type: 'play' | 'pause') {
		centerFlash = type;
		if (centerFlashTimer) clearTimeout(centerFlashTimer);
		centerFlashTimer = setTimeout(() => {
			centerFlash = null;
		}, 550);
	}

	function showStartOverHint() {
		showStartOver = true;
		if (startOverTimer) clearTimeout(startOverTimer);
		startOverTimer = setTimeout(() => {
			showStartOver = false;
		}, 8000);
	}

	function dismissStartOverHint() {
		showStartOver = false;
		if (startOverTimer) clearTimeout(startOverTimer);
	}

	function startOver() {
		dismissStartOverHint();
		seekTo(0);
	}

	function showPlaybackNotice(message: string) {
		playbackNotice = message;
		if (playbackNoticeTimer) clearTimeout(playbackNoticeTimer);
		playbackNoticeTimer = setTimeout(() => {
			playbackNotice = null;
		}, 5000);
	}

	// Jumps back to the true live edge of a growing recording/watch session -
	// omitting the start param (rather than passing `duration`) is what makes
	// the backend's tail-follow pump serve from the file's current EOF, same
	// as the initial live-edge join in loadMedia() above.
	function goLive() {
		if (!seekable || !videoElement || !isInProgress) return;
		dismissStartOverHint();
		isVideoLoading = true;
		mpegtsPlayer.teardownPlayer();
		baseOffsetSeconds = duration ?? 0;
		videoCurrentTime = 0;
		captionController.resetStretchCursor();
		captionController.refreshCaptionCues();
		mpegtsPlayer.createPlayerAt(videoElement, buildStreamUrl(undefined, currentAudioIndex));
		resetAutoHideTimer();
	}

	function togglePlay() {
		if (!videoElement) return;
		if (videoElement.paused) {
			safePlay();
			videoPaused = false;
			triggerCenterFlash('play');
			syncPlayController.sendPlay(displayedPosition);
		} else {
			videoElement.pause();
			videoPaused = true;
			triggerCenterFlash('pause');
			syncPlayController.sendPause(displayedPosition);
		}
		resetAutoHideTimer();
	}

	function toggleCaptions() {
		captionsEnabled = !captionsEnabled;
		captionController.ensureCaptionTrack();
		resetAutoHideTimer();
	}

	function selectAudioTrack(index: number) {
		const effectiveCurrentIndex = currentAudioIndex ?? 0;
		if (!seekable || index === effectiveCurrentIndex) return;
		currentAudioIndex = index;
		showAudioMenu = false;
		seekTo(displayedPosition);
	}

	async function selectCaptionTrack(track: 1 | 2) {
		if (!seekable || track === currentCaptionTrack) return;
		if (track === 2 && secondaryCaptions === 'unavailable') return;
		currentCaptionTrack = track;
		captionController.switchCaptionTrack();
		if (isInProgress) {
			await captionController.pollLiveCaptions();
		} else {
			await captionController.loadCaptions();
		}
	}

	function handleVolumeChange(newVol: number) {
		volume = Math.max(0, Math.min(1, newVol));
		if (muted && volume > 0) muted = false;
		if (videoElement) {
			videoElement.volume = volume;
			videoElement.muted = muted;
		}
		if (typeof localStorage !== 'undefined') {
			try {
				localStorage.setItem('hdhr_player_volume', String(volume));
				localStorage.setItem('hdhr_player_muted', String(muted));
			} catch {
				// ignore localStorage errors
			}
		}
		resetAutoHideTimer();
	}

	function handleMuteToggle() {
		muted = !muted;
		if (videoElement) {
			videoElement.muted = muted;
		}
		if (typeof localStorage !== 'undefined') {
			try {
				localStorage.setItem('hdhr_player_muted', String(muted));
			} catch {
				// ignore localStorage errors
			}
		}
		resetAutoHideTimer();
	}

	function handlePlaybackRateChange(rate: number) {
		playbackRate = rate;
		if (videoElement) {
			videoElement.playbackRate = rate;
		}
		resetAutoHideTimer();
	}

	function handleAspectRatioChange(ratio: 'contain' | 'cover' | 'fill' | '16:9' | '4:3') {
		aspectRatio = ratio;
		resetAutoHideTimer();
	}

	// Reloads the stream at the current playback position under the new
	// quality tier - same teardown/recreate primitive as seekTo()/goLive(),
	// but without seekTo's SyncPlay seek broadcast since the position itself
	// hasn't actually changed.
	function reloadAtCurrentQuality() {
		if (!seekable || !videoElement) return;
		const resumeAt = displayedPosition;
		isVideoLoading = true;
		mpegtsPlayer.teardownPlayer();
		baseOffsetSeconds = resumeAt;
		videoCurrentTime = 0;
		// Stale until the new stream re-reports via sampleActualMediaInfo() -
		// otherwise the panel would keep showing the previous tier's decoded
		// resolution/codec for a few seconds after switching.
		actualMediaInfo = null;
		decodedFrames = null;
		droppedFrames = null;
		captionController.resetStretchCursor();
		captionController.refreshCaptionCues();
		mpegtsPlayer.createPlayerAt(videoElement, buildStreamUrl(resumeAt, currentAudioIndex));
	}

	function handleQualityChange(next: QualityPreference) {
		if (next === quality) return;
		quality = next;
		if (next === 'auto') autoEffectiveTier = 'high';
		setQualityPreference(next);
		stallTimestamps = [];
		speedSamplesMbps = [];
		lastQualityAdjustment = null;
		reloadAtCurrentQuality();
		resetAutoHideTimer();
	}

	// Ascending order - lowest tier first. "minimal" is the floor auto mode
	// can reach on its own (see AutoTier/QUALITY_TIERS in
	// backend/app/transcoding.py); it's never offered in the manual picker.
	const TIER_ORDER: AutoTier[] = ['minimal', 'low', 'medium', 'high'];
	const AUTO_TIER_DOWNGRADE_STEPS: Record<AutoTier, AutoTier | null> = {
		high: 'medium',
		medium: 'low',
		low: 'minimal',
		minimal: null,
	};
	const AUTO_TIER_UPGRADE_STEPS: Record<AutoTier, AutoTier | null> = {
		high: null,
		medium: 'high',
		low: 'medium',
		minimal: 'low',
	};
	// Target bitrate each tier asks the backend for - mirrors
	// QUALITY_TIERS/DEFAULT_MAX_BITRATE_MBPS in backend/app/transcoding.py.
	// Used only as a relative yardstick against measured throughput, not
	// synced with a per-deployment max_bitrate_mbps override: if an admin has
	// lowered that ceiling, the real encode is at or below these numbers
	// anyway, so comparing against them just makes auto-downgrade trigger
	// a little earlier - erring toward stability, which is the goal.
	const TIER_TARGET_MBPS: Record<AutoTier, number> = {
		high: 5.0,
		medium: 3.0,
		low: 1.5,
		minimal: 0.7,
	};

	// The best (highest-quality) tier that a given sustained throughput
	// reading can plausibly support, at DOWNGRADE_MARGIN headroom. Lets a
	// severely degraded connection (well below even "low") jump straight to
	// "minimal" in one step instead of crawling down one tier per ~15s
	// sampling window while it keeps stalling along the way.
	function bestTierForSpeed(avgMbps: number): AutoTier {
		let best: AutoTier = 'minimal';
		for (const tier of TIER_ORDER) {
			if (avgMbps >= TIER_TARGET_MBPS[tier] * DOWNGRADE_MARGIN) best = tier;
		}
		return best;
	}

	// Auto quality adjustment while on "auto": a fast reactive path (repeated
	// `waiting` events - recordStallAndMaybeDowngrade below) and a slower
	// proactive path (measured throughput vs. the active tier's target
	// bitrate - sampleThroughput below, polled from attachPlayer). Stalls
	// react to a stutter that already happened; throughput sampling catches
	// a degrading connection before the buffer actually empties. Downgrades
	// are intentionally quick to trigger (favor smooth playback over
	// resolution); upgrades require a longer clean window to avoid flapping
	// back and forth at the margin.
	const STALL_WINDOW_MS = 20_000;
	const STALL_THRESHOLD = 2;
	// Throughput sampled every 5s. 3 consecutive low samples (~15s) trigger a
	// downgrade; 12 consecutive healthy samples (~60s) with no stalls in that
	// window trigger an upgrade.
	const THROUGHPUT_SAMPLE_INTERVAL_MS = 5_000;
	const DOWNGRADE_SAMPLE_COUNT = 3;
	const UPGRADE_SAMPLE_COUNT = 12;
	// Downgrade once measured speed drops within 20% of the current tier's
	// target (i.e. there's barely any headroom left); require 50% headroom
	// above the *next tier up's* target, sustained, before upgrading to it.
	const DOWNGRADE_MARGIN = 1.2;
	const UPGRADE_MARGIN = 1.5;

	function applyAutoDowngrade(reason: 'stalling' | 'throughput', target?: AutoTier) {
		const next = target ?? AUTO_TIER_DOWNGRADE_STEPS[autoEffectiveTier];
		if (!next) return;
		stallTimestamps = [];
		speedSamplesMbps = [];
		autoEffectiveTier = next;
		lastQualityAdjustment = { direction: 'down', tier: next, reason, at: Date.now() };
		reloadAtCurrentQuality();
		showPlaybackNotice(
			get(_)('player.quality_auto_downgraded', { default: 'Reduced quality due to network conditions' }),
		);
	}

	function recordStallAndMaybeDowngrade() {
		if (quality !== 'auto') return;
		const now = Date.now();
		stallTimestamps = [...stallTimestamps.filter((t) => now - t < STALL_WINDOW_MS), now];
		if (stallTimestamps.length < STALL_THRESHOLD) return;
		applyAutoDowngrade('stalling');
	}

	// Polled from attachPlayer while quality is "auto". Reads mpegts.js's
	// live loader speed (KB/s) and reacts to sustained highs/lows rather than
	// single samples, since speed naturally spikes/dips segment-to-segment.
	function sampleThroughput() {
		if (quality !== 'auto') return;
		const speedKBs = mpegtsPlayer.getStatisticsInfo()?.speed;
		if (typeof speedKBs !== 'number' || !Number.isFinite(speedKBs) || speedKBs <= 0) return;
		const speedMbps = (speedKBs * 8) / 1000;
		measuredSpeedMbps = speedMbps;
		speedSamplesMbps = [...speedSamplesMbps, speedMbps].slice(-UPGRADE_SAMPLE_COUNT);

		const downgradeWindow = speedSamplesMbps.slice(-DOWNGRADE_SAMPLE_COUNT);
		if (downgradeWindow.length >= DOWNGRADE_SAMPLE_COUNT) {
			const avg = downgradeWindow.reduce((a, b) => a + b, 0) / downgradeWindow.length;
			if (avg < TIER_TARGET_MBPS[autoEffectiveTier] * DOWNGRADE_MARGIN) {
				const target = bestTierForSpeed(avg);
				if (TIER_ORDER.indexOf(target) < TIER_ORDER.indexOf(autoEffectiveTier)) {
					applyAutoDowngrade('throughput', target);
					return;
				}
			}
		}

		const nextUp = AUTO_TIER_UPGRADE_STEPS[autoEffectiveTier];
		if (!nextUp) return;
		if (speedSamplesMbps.length < UPGRADE_SAMPLE_COUNT) return;
		if (stallTimestamps.length > 0) return;
		const avgAll = speedSamplesMbps.reduce((a, b) => a + b, 0) / speedSamplesMbps.length;
		if (avgAll < TIER_TARGET_MBPS[nextUp] * UPGRADE_MARGIN) return;
		speedSamplesMbps = [];
		autoEffectiveTier = nextUp;
		lastQualityAdjustment = { direction: 'up', tier: nextUp, reason: 'recovered', at: Date.now() };
		reloadAtCurrentQuality();
		showPlaybackNotice(
			get(_)('player.quality_auto_upgraded', { default: 'Network improved - increasing quality' }),
		);
	}

	function handleToggleFavorite() {
		if (channelNumber && onToggleFavorite) {
			onToggleFavorite(channelNumber);
		}
		resetAutoHideTimer();
	}

	function selectDrawerChannel(target: HDHomeRunChannel) {
		showChannelDrawer = false;
		if (target.channel_number === channelNumber) return;
		onChannelChange?.(target);
	}

	async function toggleFullscreen() {
		if (typeof document === 'undefined') return;
		try {
			if (isFullscreen) {
				if (document.exitFullscreen) {
					await document.exitFullscreen();
				} else if ((document as unknown as { webkitExitFullscreen?: () => Promise<void> }).webkitExitFullscreen) {
					await (document as unknown as { webkitExitFullscreen: () => Promise<void> }).webkitExitFullscreen();
				}
			} else {
				const target = overlayEl ?? videoElement;
				if (target?.requestFullscreen) {
					await target.requestFullscreen();
				} else if (
					(target as unknown as { webkitRequestFullscreen?: () => Promise<void> })?.webkitRequestFullscreen
				) {
					await (
						target as unknown as { webkitRequestFullscreen: () => Promise<void> }
					).webkitRequestFullscreen();
				} else if (
					(videoElement as unknown as { webkitEnterFullscreen?: () => void })?.webkitEnterFullscreen
				) {
					(videoElement as unknown as { webkitEnterFullscreen: () => void }).webkitEnterFullscreen();
				}
			}
		} catch {
			// ignore
		}
		resetAutoHideTimer();
	}

	async function togglePip() {
		if (!videoElement || typeof document === 'undefined') return;
		try {
			if (document.pictureInPictureElement) {
				await document.exitPictureInPicture();
			} else if (videoElement.requestPictureInPicture) {
				await videoElement.requestPictureInPicture();
			}
		} catch {
			// ignore
		}
		resetAutoHideTimer();
	}

	function resetAutoHideTimer() {
		showControls = true;
		if (autoHideTimer) {
			clearTimeout(autoHideTimer);
			autoHideTimer = undefined;
		}
		const hasActiveMenu =
			showRecordMenu ||
			showOptionsDialog ||
			showAudioMenu ||
			showSettingsMenu ||
			showPlaybackInfo ||
			showSyncPlayModal ||
			showChannelDrawer;

		if (!videoPaused && !hasActiveMenu) {
			autoHideTimer = setTimeout(() => {
				showControls = false;
			}, 3500);
		}
	}

	function handleMouseMove() {
		resetAutoHideTimer();
	}

	function handleKeydown(e: KeyboardEvent) {
		// The component now stays mounted (and this <svelte:window> listener
		// stays bound) while mini elsewhere in the app, so keystrokes must not
		// hijack playback unless the full player actually has the user's focus.
		if (displayMode !== 'full') return;
		const target = e.target as HTMLElement | null;
		if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
			if (e.key === 'Escape') {
				(target as HTMLElement).blur();
			}
			return;
		}

		resetAutoHideTimer();
		if (e.key === 'Escape') {
			if (showChannelDrawer) {
				showChannelDrawer = false;
			} else if (showSyncPlayModal) {
				showSyncPlayModal = false;
			} else if (showPlaybackInfo) {
				showPlaybackInfo = false;
			} else if (showAudioMenu) {
				showAudioMenu = false;
			} else if (showSettingsMenu) {
				showSettingsMenu = false;
			} else if (showRecordMenu) {
				showRecordMenu = false;
			} else if (showOptionsDialog) {
				showOptionsDialog = false;
			} else if (isFullscreen) {
				toggleFullscreen();
			} else {
				onClose();
			}
		} else if (e.key === ' ') {
			e.preventDefault();
			togglePlay();
		} else if (e.key === 'f' || e.key === 'F') {
			e.preventDefault();
			toggleFullscreen();
		} else if (e.key === 'm' || e.key === 'M') {
			e.preventDefault();
			handleMuteToggle();
		} else if (e.key === 'p' || e.key === 'P') {
			if (pipSupported) {
				e.preventDefault();
				togglePip();
			}
		} else if ((e.key === 'ArrowLeft' || e.key === 'j') && seekable) {
			rewind(10);
		} else if ((e.key === 'ArrowRight' || e.key === 'l') && seekable) {
			fastForward(10);
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			handleVolumeChange(volume + 0.05);
		} else if (e.key === 'ArrowDown') {
			e.preventDefault();
			handleVolumeChange(volume - 0.05);
		} else if (e.key === 'c' && hasCaptions) {
			toggleCaptions();
		} else if (e.key === 'r' && canRecord) {
			showRecordMenu = !showRecordMenu;
		}
	}

	const recordingActionsController = createRecordingActionsController({
		getEffectiveAiring: () => effectiveAiring,
		getChannelName: () => channelName,
		getChannelNumber: () => channelNumber,
		getIsWatchSession: () => Boolean(isWatchSession),
		getWatchSessionId: () => watchSessionId,
		getCurrentRule: () => currentRule,
		getRecordingRules: () => recordingRules,
		setRecordingRules: (rules) => {
			recordingRules = rules;
		},
		setErrorMessage: (msg) => {
			errorMessage = msg;
		},
		setInternalRecordingLoading: (loading) => {
			internalRecordingLoading = loading;
		},
		setShowRecordMenu: (show) => {
			showRecordMenu = show;
		},
		setShowOptionsDialog: (show) => {
			showOptionsDialog = show;
		},
		getOnRecordEpisode: () => onRecordEpisode,
		getOnRecordSeries: () => onRecordSeries,
		getOnCancelRule: () => onCancelRule,
		getOnUpdateRule: () => onUpdateRule,
		translate: (key) => get(_)(key),
	});

	const handleRecordEpisode = (options?: RecordingRuleOptions) => recordingActionsController.handleRecordEpisode(options);
	const handleRecordSeries = (options?: RecordingRuleOptions) => recordingActionsController.handleRecordSeries(options);
	const handleCancelRecording = () => recordingActionsController.handleCancelRecording();
	const handleConfirmOptions = (mode: 'episode' | 'series', options: RecordingRuleOptions) =>
		recordingActionsController.handleConfirmOptions(mode, options);

	function handlePopout() {
		if (videoElement) {
			videoElement.pause();
		}
		const chNum = channel?.channel_number ?? (channelNumber || undefined);
		openPopoutPlayer({
			channel: chNum,
			recording: recordingId ?? undefined,
			playUrl: playUrl ?? undefined,
			title: title,
			t: videoCurrentTime > 0 ? videoCurrentTime : undefined,
		});
		onClose();
	}

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
		node.volume = volume;
		node.muted = muted;
		node.playbackRate = playbackRate;
		isVideoLoading = true;

		const handleLoadStart = () => { isVideoLoading = true; };
		const handleWaiting = () => {
			isVideoLoading = true;
			// Only counts as a stall worth reacting to once playback has
			// actually gotten underway - excludes the initial pre-roll
			// buffering wait and the one `waiting` tick a seek/reload itself
			// causes (both already handled by isVideoLoading above).
			if (node.currentTime > 0) recordStallAndMaybeDowngrade();
		};
		const handleSeeking = () => { isVideoLoading = true; };
		const handlePlaying = () => { isVideoLoading = false; videoPaused = false; };
		const handleCanPlay = () => { isVideoLoading = false; };
		const handleLoadedData = () => { isVideoLoading = false; };
		const handleTimeUpdate = () => {
			if (isVideoLoading && node.currentTime > 0) isVideoLoading = false;
			if (syncPlayStatus !== 'disconnected') {
				syncPlayController.checkAndApplyDrift();
			}
		};

		node.addEventListener('loadstart', handleLoadStart);
		node.addEventListener('waiting', handleWaiting);
		node.addEventListener('seeking', handleSeeking);
		node.addEventListener('playing', handlePlaying);
		node.addEventListener('canplay', handleCanPlay);
		node.addEventListener('loadeddata', handleLoadedData);
		node.addEventListener('timeupdate', handleTimeUpdate);

		loadMedia(node);
		startThroughputPolling();

		return {
			destroy() {
				destroyed = true;
				syncPlayController.destroy();
				node.removeEventListener('loadstart', handleLoadStart);
				node.removeEventListener('waiting', handleWaiting);
				node.removeEventListener('seeking', handleSeeking);
				node.removeEventListener('playing', handlePlaying);
				node.removeEventListener('canplay', handleCanPlay);
				node.removeEventListener('loadeddata', handleLoadedData);
				node.removeEventListener('timeupdate', handleTimeUpdate);
				stopPolling();
				stopCaptionPolling();
				stopThroughputPolling();
				if (autoHideTimer) clearTimeout(autoHideTimer);
				if (centerFlashTimer) clearTimeout(centerFlashTimer);
				if (startOverTimer) clearTimeout(startOverTimer);
				if (playbackNoticeTimer) clearTimeout(playbackNoticeTimer);
				if (autoSkipPillTimer) clearTimeout(autoSkipPillTimer);
				mpegtsPlayer.teardownPlayer();
				airplayController.destroy();
				videoElement = null;
				captionController.teardown();
				captionCues = [];
			},
		};
	}

	async function loadMedia(node: HTMLVideoElement): Promise<void> {
		if (seekable) {
			await loadDetail();
			if (destroyed) return;
			// isWatchSession is known synchronously the moment the watch session
			// was created (routes/+page.svelte's watchChannel()/
			// watchLiveForRecording()) - it must join at the live edge
			// regardless of what loadDetail() reports. Relying on isInProgress
			// alone is a race: if that fetch is slow, fails, or the backend
			// hasn't caught up yet, isInProgress stays at its default `false`
			// and playback silently falls through to "start at 0" below -
			// exactly the "lands at the beginning instead of live" bug.
			if (isWatchSession || isInProgress) {
				baseOffsetSeconds = duration ?? 0;
				mpegtsPlayer.createPlayerAt(node, buildStreamUrl(undefined, currentAudioIndex));
				captionController.pollLiveCaptions();
				startPolling();
				startCaptionPolling();
				showStartOverHint();
			} else {
				baseOffsetSeconds = 0;
				mpegtsPlayer.createPlayerAt(node, buildStreamUrl(0, currentAudioIndex));
				loadThumbnails();
				captionController.loadCaptions();
			}
		} else {
			mpegtsPlayer.createPlayerAt(node, src);
		}
	}

	// Identifies "what should currently be playing" - changes whenever the
	// user zaps to a different live channel or a different recording/watch
	// session via the in-player channel drawer (selectDrawerChannel ->
	// onChannelChange -> parent reassigns props to a new channel while this
	// component instance, and its <video> element, stay mounted so
	// fullscreen/PiP survive the swap - see requestFullscreen() targeting
	// overlayEl). Since attachPlayer's use: action only runs once at mount,
	// swapping src/playUrl/etc alone never re-triggers mpegts playback -
	// the effect below is what notices the identity changed and reloads.
	const mediaKey = $derived(
		`${seekable ? 'rec' : 'live'}:${channelNumber ?? ''}:${recordingId ?? ''}:${watchSessionId ?? ''}:${playUrl ?? ''}:${src}`,
	);

	function switchMedia() {
		if (!videoElement || destroyed) return;
		stopPolling();
		stopCaptionPolling();
		mpegtsPlayer.teardownPlayer();
		isVideoLoading = true;
		duration = null;
		isInProgress = false;
		videoInfo = null;
		actualMediaInfo = null;
		decodedFrames = null;
		droppedFrames = null;
		audioTracks = [];
		currentAudioIndex = null;
		hasCaptions = false;
		secondaryCaptions = null;
		thumbnailsAvailable = false;
		thumbnailCues = [];
		thumbSpriteUrl = '';
		transcodeInfo = null;
		commercialSegments = [];
		lastAutoSkippedSegmentStart = null;
		captionCues = [];
		videoCurrentTime = 0;
		baseOffsetSeconds = 0;
		if (quality === 'auto') autoEffectiveTier = 'high';
		stallTimestamps = [];
		speedSamplesMbps = [];
		measuredSpeedMbps = null;
		lastQualityAdjustment = null;
		dismissStartOverHint();
		captionController.resetStretchCursor();
		loadMedia(videoElement);
	}

	// Skips the initial run - attachPlayer's own mount call already loads
	// the first channel/recording - and reloads only on later changes.
	let initializedMediaKey: string | undefined;
	$effect(() => {
		const key = mediaKey;
		if (initializedMediaKey === undefined) {
			initializedMediaKey = key;
			return;
		}
		if (key === initializedMediaKey) return;
		initializedMediaKey = key;
		switchMedia();
	});

	// Fullscreen & PiP Event Listeners
	$effect(() => {
		if (typeof document === 'undefined') return;
		const updateFullscreen = () => {
			isFullscreen = Boolean(
				document.fullscreenElement ||
					(document as unknown as { webkitFullscreenElement?: Element }).webkitFullscreenElement,
			);
		};
		document.addEventListener('fullscreenchange', updateFullscreen);
		document.addEventListener('webkitfullscreenchange', updateFullscreen);

		if ('pictureInPictureEnabled' in document) {
			pipSupported = Boolean(document.pictureInPictureEnabled);
		}

		return () => {
			document.removeEventListener('fullscreenchange', updateFullscreen);
			document.removeEventListener('webkitfullscreenchange', updateFullscreen);
		};
	});

	async function buildCastContentUrl(): Promise<{ url: string; sessionId: string }> {
		const session =
			seekable && playUrl
				? await api.createRecordingHlsSessionForCast({
						url: playUrl,
						recordingId,
						start: baseOffsetSeconds + videoCurrentTime,
						audioIndex: currentAudioIndex ?? undefined,
					})
				: await api.createChannelHlsSessionForCast(channelNumber ?? '');
		return { url: session.playlist_url, sessionId: session.session_id };
	}

	// AirPlay Controller
	const airplayController = createAirPlayController({
		getVideoElement: () =>
			videoElement as (HTMLVideoElement & { webkitShowPlaybackTargetPicker?: () => void }) | null,
		getDestroyed: () => destroyed,
		getSeekable: () => seekable,
		getBaseOffsetSeconds: () => baseOffsetSeconds,
		setBaseOffsetSeconds: (value) => {
			baseOffsetSeconds = value;
		},
		getVideoCurrentTime: () => videoCurrentTime,
		setVideoCurrentTime: (value) => {
			videoCurrentTime = value;
		},
		getCurrentAudioIndex: () => currentAudioIndex,
		getSrc: () => src,
		buildStreamUrl,
		buildCastContentUrl,
		onAvailabilityChange: (available) => {
			airplayAvailable = available;
		},
		teardownMpegtsPlayer: () => mpegtsPlayer.teardownPlayer(),
		createMpegtsPlayerAt: (video, streamUrl) => mpegtsPlayer.createPlayerAt(video, streamUrl),
		safePlay,
		refreshCaptions: () => {
			captionController.resetStretchCursor();
			captionController.refreshCaptionCues();
		},
	});

	$effect(() => {
		return airplayController.attachVideoElement(
			videoElement as (HTMLVideoElement & { webkitShowPlaybackTargetPicker?: () => void }) | null,
		);
	});

	function showAirPlayPicker() {
		airplayController.showAirPlayPicker();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
	class="overlay"
	class:mini={displayMode === 'mini'}
	class:hide-cursor={!showControls && !videoPaused}
	role="dialog"
	aria-label={title}
	tabindex="-1"
	bind:this={overlayEl}
	onmousemove={handleMouseMove}
	use:portal
>
	{#if displayMode === 'full'}
	<!-- Top Header -->
	<div class="header-wrap" class:visible={showControls || videoPaused}>
		<PlayerHeader
			{title}
			subtitle={episodeSubtitle}
			{channelNumber}
			{channelName}
			{canRecord}
			{currentRule}
			{isPending}
			{isActionLoading}
			{channels}
			{effectiveAiring}
			{officialDvrActive}
			{airplayAvailable}
			syncPlayActive={Boolean(syncPlayRoom)}
			syncPlayParticipantsCount={syncPlayRoom?.participants?.length ?? 0}
			onToggleSyncPlay={() => (showSyncPlayModal = !showSyncPlayModal)}
			bind:showRecordMenu
			bind:showOptionsDialog
			{showAirPlayPicker}
			{buildCastContentUrl}
			onCastingChange={(casting) => {
				if (videoElement) {
					if (casting) videoElement.pause();
					else safePlay();
				}
			}}
			onRecordEpisode={handleRecordEpisode}
			onRecordSeries={handleRecordSeries}
			onCancelRecording={handleCancelRecording}
			onConfirmOptions={handleConfirmOptions}
			{onToggleMultiView}
			onPopout={allowPopout ? (onPopout ?? handlePopout) : undefined}
			{onClose}
		/>
	</div>

	{#if errorMessage}
		<p class="error">
			{errorMessage}
			{#if errorDetail}
				<span class="error-detail">{errorDetail}</span>
			{/if}
		</p>
	{/if}
	{/if}

	<!-- Video Area -->
	<div
		class="video-container"
		class:aspect-16-9={aspectRatio === '16:9'}
		class:aspect-4-3={aspectRatio === '4:3'}
		onclick={togglePlay}
		ondblclick={displayMode === 'full' ? toggleFullscreen : undefined}
		role="button"
		tabindex="0"
		aria-label="Video playback"
		onkeydown={(e) => e.key === ' ' && togglePlay()}
	>
		<!-- svelte-ignore a11y_media_has_caption -->
		<video
			autoplay
			playsinline
			controls={false}
			class="video"
			class:fit-cover={aspectRatio === 'cover'}
			class:fit-fill={aspectRatio === 'fill'}
			class:fit-contain={aspectRatio === 'contain' || aspectRatio === '16:9' || aspectRatio === '4:3'}
			use:attachPlayer
			bind:currentTime={videoCurrentTime}
			onplay={() => (videoPaused = false)}
			onpause={() => (videoPaused = true)}
			crossorigin="use-credentials"
			{...{ 'x-webkit-airplay': 'allow' }}
		></video>

		{#if displayMode === 'full'}
			<!-- Center Play/Pause Flash Ripple Animation -->
			{#if centerFlash}
				<div class="center-flash-ripple" aria-hidden="true">
					<PlayerIcon name={centerFlash} size={48} />
				</div>
			{/if}

			<!-- Custom Caption Overlay -->
			{#if captionsEnabled && activeCaptionLines.length > 0}
				<div class="caption-overlay" class:with-footer={showControls} aria-live="polite">
					{#each activeCaptionLines as line, i (i + line)}
						<div class="caption-line">{line}</div>
					{/each}
				</div>
			{/if}

			<!-- Skip Commercial Prompt -->
			{#if $autoSkipCommercials}
				{#if showAutoSkipPill}
					<div class="skip-commercial-overlay auto-skip-pill" class:with-footer={showControls} aria-live="polite">
						{$_('player.commercial_skipped', { default: 'Commercial skipped' })}
					</div>
				{/if}
			{:else if activeCommercialSegment}
				<div class="skip-commercial-overlay" class:with-footer={showControls}>
					<button
						type="button"
						class="skip-commercial-btn"
						onclick={(e) => {
							e.stopPropagation();
							skipCommercial();
						}}
					>
						{$_('player.skip_commercial', { default: 'Skip Commercial' })}
					</button>
				</div>
			{/if}

			<!-- Loading Quip & Spinner Overlay -->
			<LoadingQuipOverlay visible={isVideoLoading && !errorMessage} />

			<!-- "You're watching live - want the beginning instead?" quick switch -->
			{#if showStartOver}
				<div class="start-over-overlay" aria-hidden={!showStartOver}>
					<button type="button" class="start-over-btn" onclick={(e) => { e.stopPropagation(); startOver(); }}>
						{$_('player.start_from_beginning', { default: '⏮ Start from Beginning' })}
					</button>
					<button
						type="button"
						class="start-over-dismiss"
						aria-label={$_('common.dismiss', { default: 'Dismiss' })}
						onclick={(e) => { e.stopPropagation(); dismissStartOverHint(); }}
					>
						✕
					</button>
				</div>
			{/if}

			<!-- Non-blocking playback notices (e.g. auto quality downgrade) -->
			{#if playbackNotice}
				<div class="playback-notice-overlay" aria-live="polite">{playbackNotice}</div>
			{/if}
		{/if}
	</div>

	{#if displayMode === 'mini'}
		<MiniPlayer
			{title}
			subtitle={episodeSubtitle}
			paused={videoPaused}
			{isVideoLoading}
			onTogglePlay={togglePlay}
			{onClose}
			onExpand={() => onExpand?.()}
		/>
	{/if}

	{#if displayMode === 'full'}
	<!-- Bottom Footer -->
	<div class="footer-wrap" class:visible={showControls || videoPaused}>
		<PlayerFooter
			{displayedPosition}
			{duration}
			{isInProgress}
			{seekable}
			{thumbnailsAvailable}
			{thumbSpriteUrl}
			{thumbnailCues}
			{commercialSegments}
			paused={videoPaused}
			{volume}
			{muted}
			{isFavorited}
			{channelNumber}
			{pipSupported}
			{isPipActive}
			{isFullscreen}
			{captionsEnabled}
			{hasCaptions}
			{audioTracks}
			{currentAudioIndex}
			{currentCaptionTrack}
			{secondaryCaptions}
			scheduledEndTime={effectiveAiring?.end ?? recordEndTimestamp}
			{isLive}
			{playbackRate}
			{aspectRatio}
			{quality}
			bind:showAudioMenu
			bind:showSettingsMenu
			onSeek={seekTo}
			onGoLive={goLive}
			onTogglePlay={togglePlay}
			onRewind={rewind}
			onFastForward={fastForward}
			onVolumeChange={handleVolumeChange}
			onMuteToggle={handleMuteToggle}
			onToggleFavorite={handleToggleFavorite}
			onTogglePip={togglePip}
			onToggleFullscreen={toggleFullscreen}
			onToggleCaptions={toggleCaptions}
			onSelectAudioTrack={selectAudioTrack}
			onSelectCaptionTrack={selectCaptionTrack}
			onPlaybackRateChange={handlePlaybackRateChange}
			onAspectRatioChange={handleAspectRatioChange}
			onQualityChange={handleQualityChange}
			syncPlayActive={Boolean(syncPlayRoom)}
			syncPlayParticipantsCount={syncPlayRoom?.participants?.length ?? 0}
			onToggleSyncPlay={() => (showSyncPlayModal = !showSyncPlayModal)}
			onTogglePlaybackInfo={() => (showPlaybackInfo = !showPlaybackInfo)}
			{channelSwitcherAvailable}
			onToggleChannelDrawer={() => (showChannelDrawer = !showChannelDrawer)}
		/>
	</div>

	<!-- Playback Info Modal (Stats for Nerds) -->
	{#if showPlaybackInfo}
		<div class="info-overlay-modal" role="dialog" aria-label={$_('player.playback_info', { default: 'Playback Info' })}>
			<div class="info-card">
				<div class="info-header">
					<h3>{$_('player.playback_info', { default: 'Playback Info' })}</h3>
					<button type="button" class="info-close" onclick={() => (showPlaybackInfo = false)}>✕</button>
				</div>
				<div class="info-body">
					<div class="info-row">
						<span class="label">{$_('player.container', { default: 'Container' })}:</span>
						<span class="value uppercase">MPEG-TS</span>
					</div>
					{#if transcodeInfo}
						<div class="info-row">
							<span class="label">{$_('player.transcoding', { default: 'Transcoding' })}:</span>
							<span class="value">
								{#if transcodeInfo.transcoding}
									{$_('player.transcoding_via', { values: { preset: transcodeInfo.preset_label }, default: `Transcoding (${transcodeInfo.preset_label})` })}
									{#if transcodeInfo.hardware}<span class="hw-badge">HW</span>{/if}
								{:else}
									{$_('player.direct_passthrough', { default: 'Direct Passthrough' })}
								{/if}
							</span>
						</div>
					{/if}
					{#if seekable}
						<div class="info-row">
							<span class="label">{$_('player.quality', { default: 'Quality' })}:</span>
							<span class="value uppercase">
								{#if quality === 'auto'}
									{$_('player.quality_auto_at', { values: { tier: autoEffectiveTier }, default: `Auto (${autoEffectiveTier})` })}
								{:else}
									{quality}
								{/if}
							</span>
						</div>
						{#if quality === 'auto' && lastQualityAdjustment}
							<div class="info-row">
								<span class="label">{$_('player.quality_last_change', { default: 'Last change' })}:</span>
								<span class="value">
									{#if lastQualityAdjustment.direction === 'down'}
										{lastQualityAdjustment.reason === 'stalling'
											? $_('player.quality_reason_stalling', { values: { tier: lastQualityAdjustment.tier }, default: `Reduced to ${lastQualityAdjustment.tier} after repeated stalls` })
											: $_('player.quality_reason_throughput', { values: { tier: lastQualityAdjustment.tier }, default: `Reduced to ${lastQualityAdjustment.tier} - network throughput too low` })}
									{:else}
										{$_('player.quality_reason_recovered', { values: { tier: lastQualityAdjustment.tier }, default: `Increased to ${lastQualityAdjustment.tier} - network improved` })}
									{/if}
									· {formatAgo((Date.now() - lastQualityAdjustment.at) / 1000)} {$_('player.ago', { default: 'ago' })}
								</span>
							</div>
						{/if}
						{#if measuredSpeedMbps !== null}
							<div class="info-row">
								<span class="label">{$_('player.network_speed', { default: 'Network Speed' })}:</span>
								<span class="value">{measuredSpeedMbps.toFixed(1)} Mbps</span>
							</div>
						{/if}
					{/if}
					{#if isInProgress && !videoInfo && audioTracks.length === 0}
						<div class="info-row">
							<span class="value">{$_('player.analyzing_stream', { default: 'Analyzing stream…' })}</span>
						</div>
					{/if}
					{#if actualMediaInfo}
						<div class="info-section-heading">{$_('player.playing_now', { default: 'Playing Now (Actual)' })}</div>
						<div class="info-row">
							<span class="label">Codec:</span>
							<span class="value uppercase">{actualMediaInfo.codec ?? $_('common.unknown', { default: 'Unknown' })}</span>
						</div>
						{#if actualMediaInfo.width && actualMediaInfo.height}
							<div class="info-row">
								<span class="label">{$_('player.resolution', { default: 'Resolution' })}:</span>
								<span class="value">{actualMediaInfo.width}×{actualMediaInfo.height}</span>
							</div>
						{/if}
						{#if actualMediaInfo.fps}
							<div class="info-row">
								<span class="label">Framerate:</span>
								<span class="value">{actualMediaInfo.fps} fps</span>
							</div>
						{/if}
						{#if actualMediaInfo.audioCodec}
							<div class="info-row">
								<span class="label">{$_('player.audio_codec', { default: 'Audio Codec' })}:</span>
								<span class="value uppercase">{actualMediaInfo.audioCodec}</span>
							</div>
						{/if}
						{#if decodedFrames !== null}
							<div class="info-row">
								<span class="label">{$_('player.dropped_frames', { default: 'Dropped Frames' })}:</span>
								<span class="value">{droppedFrames ?? 0} / {decodedFrames}</span>
							</div>
						{/if}
					{/if}
					{#if videoInfo}
						<div class="info-section-heading">{$_('player.source_video', { default: 'Source (Original)' })}</div>
						<div class="info-row">
							<span class="label">Codec:</span>
							<span class="value uppercase">{videoInfo.codec ?? $_('common.unknown', { default: 'Unknown' })}</span>
						</div>
						{#if videoInfo.width && videoInfo.height}
							<div class="info-row">
								<span class="label">{$_('player.resolution', { default: 'Resolution' })}:</span>
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
						<div class="info-section-heading">{$_('player.audio', { default: 'Audio' })}</div>
						{#each audioTracks as track (track.index)}
							<div class="info-row">
								<span class="label">Track {track.index + 1}:</span>
								<span class="value uppercase">{track.codec ?? $_('common.unknown', { default: 'Unknown' })} · {track.channels ?? '?'}ch</span>
							</div>
						{/each}
					{/if}
					<div class="info-row">
						<span class="label">{$_('player.duration', { default: 'Duration' })}:</span>
						<span class="value">{duration !== null ? formatTime(duration) : $_('common.unknown', { default: 'Live / Unknown' })}</span>
					</div>
				</div>
			</div>
		</div>
	{/if}

	<!-- SyncPlay Watch Party Modal -->
	{#if showSyncPlayModal}
		<SyncPlayModal
			show={showSyncPlayModal}
			room={syncPlayRoom}
			roomCode={syncPlayRoom?.room_code ?? null}
			participants={syncPlayRoom?.participants ?? []}
			isHost={syncPlayController.getIsHost()}
			pingMs={syncPlayPingMs}
			status={syncPlayStatus}
			currentContent={currentSyncContent}
			onJoinRoom={(code) => syncPlayController.joinRoom(code)}
			onCreateRoom={async () => {
				await syncPlayController.createRoom(currentSyncContent);
			}}
			onLeaveRoom={() => syncPlayController.leaveRoom()}
			onTransferHost={(targetId) => syncPlayController.transferHost(targetId)}
			onClose={() => {
				showSyncPlayModal = false;
			}}
		/>
	{/if}

	<!-- Quick Channel Switcher -->
	{#if showChannelDrawer}
		<PlayerChannelDrawer
			{channels}
			{favoriteChannels}
			currentChannelNumber={channelNumber}
			onSelect={selectDrawerChannel}
			onClose={() => (showChannelDrawer = false)}
		/>
	{/if}
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
		overflow: hidden;
		user-select: none;
	}

	.overlay.hide-cursor {
		cursor: none;
	}

	/* Docked mini box (CAST-4): playback keeps running elsewhere in the app,
	   so this must not blanket-cover the viewport like the full overlay does. */
	.overlay.mini {
		position: fixed;
		inset: auto;
		bottom: 1rem;
		right: 1rem;
		width: 200px;
		height: 120px;
		z-index: 200;
		border-radius: 0.5rem;
		box-shadow: 0 8px 28px rgba(0, 0, 0, 0.6);
	}

	.header-wrap,
	.footer-wrap {
		opacity: 0;
		pointer-events: none;
		transition: opacity 0.25s ease-in-out;
	}

	.header-wrap.visible,
	.footer-wrap.visible {
		opacity: 1;
		pointer-events: auto;
	}

	.error {
		position: absolute;
		top: 4.5rem;
		left: 1rem;
		right: 1rem;
		z-index: 140;
		margin: 0;
		padding: 0.75rem 1rem;
		color: #ffb4b4;
		background: rgba(224, 90, 90, 0.25);
		border: 1px solid rgba(224, 90, 90, 0.5);
		border-radius: 0.5rem;
		backdrop-filter: blur(8px);
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
		align-items: center;
		justify-content: center;
		min-height: 0;
		background: #000;
		outline: none;
		cursor: pointer;
	}

	.video {
		width: 100%;
		height: 100%;
		min-height: 0;
		background: #000;
	}

	.video.fit-contain {
		object-fit: contain;
	}

	.video.fit-cover {
		object-fit: cover;
	}

	.video.fit-fill {
		object-fit: fill;
	}

	.video-container.aspect-16-9 .video {
		aspect-ratio: 16 / 9;
		max-height: 100%;
		width: auto;
	}

	.video-container.aspect-4-3 .video {
		aspect-ratio: 4 / 3;
		max-height: 100%;
		width: auto;
	}

	.center-flash-ripple {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: 5rem;
		height: 5rem;
		border-radius: 50%;
		background: rgba(0, 0, 0, 0.65);
		color: #ffffff;
		display: flex;
		align-items: center;
		justify-content: center;
		pointer-events: none;
		z-index: 110;
		box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
		animation: flash-pulse 0.5s ease-out forwards;
	}

	@keyframes flash-pulse {
		0% {
			opacity: 0;
			transform: translate(-50%, -50%) scale(0.7);
		}
		30% {
			opacity: 1;
			transform: translate(-50%, -50%) scale(1.1);
		}
		100% {
			opacity: 0;
			transform: translate(-50%, -50%) scale(1.3);
		}
	}

	.caption-overlay {
		position: absolute;
		bottom: 2rem;
		left: 50%;
		transform: translateX(-50%);
		max-width: 85%;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.25rem;
		pointer-events: none;
		z-index: 105;
		text-align: center;
		transition: bottom 0.25s ease;
	}

	.caption-overlay.with-footer {
		bottom: 6rem;
	}

	.caption-line {
		display: inline-block;
		background: rgba(0, 0, 0, 0.85);
		color: #ffffff;
		padding: 0.25rem 0.65rem;
		border-radius: 0.25rem;
		font-size: 1.15rem;
		line-height: 1.4;
		font-weight: 500;
		text-shadow: 0 1px 2px rgba(0, 0, 0, 0.9);
		box-shadow: 0 2px 6px rgba(0, 0, 0, 0.6);
		white-space: pre-wrap;
		word-break: break-word;
	}

	.skip-commercial-overlay {
		position: absolute;
		bottom: 2rem;
		right: 1.25rem;
		z-index: 106;
		transition: bottom 0.25s ease;
	}

	.skip-commercial-overlay.with-footer {
		bottom: 6rem;
	}

	.skip-commercial-btn {
		background: rgba(22, 22, 26, 0.96);
		backdrop-filter: blur(16px);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.4rem;
		color: #ffffff;
		font-size: 0.9rem;
		font-weight: 600;
		padding: 0.55rem 1rem;
		cursor: pointer;
		box-shadow: 0 6px 20px rgba(0, 0, 0, 0.6);
		transition: background 0.15s ease;
	}

	.skip-commercial-btn:hover {
		background: rgba(56, 189, 248, 0.25);
		border-color: #38bdf8;
	}

	.skip-commercial-overlay.auto-skip-pill {
		background: rgba(22, 22, 26, 0.96);
		backdrop-filter: blur(16px);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.4rem;
		color: #ffffff;
		font-size: 0.9rem;
		font-weight: 600;
		padding: 0.55rem 1rem;
		box-shadow: 0 6px 20px rgba(0, 0, 0, 0.6);
	}

	.start-over-overlay {
		position: absolute;
		top: 1.25rem;
		left: 1.25rem;
		z-index: 106;
		display: flex;
		align-items: center;
		gap: 0.4rem;
		animation: popover-fade-in 0.2s ease;
	}

	.start-over-btn {
		background: rgba(22, 22, 26, 0.96);
		backdrop-filter: blur(16px);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.4rem;
		color: #ffffff;
		font-size: 0.85rem;
		font-weight: 600;
		padding: 0.55rem 0.9rem;
		cursor: pointer;
		box-shadow: 0 6px 20px rgba(0, 0, 0, 0.6);
		transition: background 0.15s ease;
	}

	.start-over-btn:hover {
		background: rgba(56, 189, 248, 0.25);
		border-color: #38bdf8;
	}

	.start-over-dismiss {
		background: rgba(22, 22, 26, 0.96);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 50%;
		color: rgba(255, 255, 255, 0.7);
		width: 1.9rem;
		height: 1.9rem;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		font-size: 0.75rem;
	}

	.start-over-dismiss:hover {
		color: #ffffff;
	}

	.playback-notice-overlay {
		position: absolute;
		top: 1.25rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 106;
		background: rgba(22, 22, 26, 0.96);
		backdrop-filter: blur(16px);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.4rem;
		color: #ffffff;
		font-size: 0.82rem;
		padding: 0.5rem 0.9rem;
		box-shadow: 0 6px 20px rgba(0, 0, 0, 0.6);
		animation: notice-fade-in 0.2s ease;
	}

	@keyframes notice-fade-in {
		from {
			opacity: 0;
			transform: translateX(-50%) translateY(-6px);
		}
		to {
			opacity: 1;
			transform: translateX(-50%) translateY(0);
		}
	}

	@keyframes popover-fade-in {
		from {
			opacity: 0;
			transform: translateY(-6px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.info-overlay-modal {
		position: absolute;
		inset: 0;
		z-index: 160;
		background: rgba(0, 0, 0, 0.65);
		backdrop-filter: blur(6px);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.info-card {
		background: rgba(28, 28, 34, 0.96);
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

	.info-close:hover {
		color: #ffffff;
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
