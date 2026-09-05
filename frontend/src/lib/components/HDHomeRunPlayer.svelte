<script lang="ts">
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import {
		api,
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
	import PlayerHeader from './player/PlayerHeader.svelte';
	import PlayerFooter from './player/PlayerFooter.svelte';
	import PlayerIcon from './player/icons/PlayerIcon.svelte';
	import LoadingQuipOverlay from './player/LoadingQuipOverlay.svelte';
	import SyncPlayModal from './player/SyncPlayModal.svelte';
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
			channelNumber?: string,
			start?: number | null,
			options?: RecordingRuleOptions,
		) => Promise<void> | void;
		onRecordSeries?: (
			seriesId: string,
			channelNumber?: string,
			options?: RecordingRuleOptions,
		) => Promise<void> | void;
		onUpdateRule?: (
			ruleId: string,
			mode: 'episode' | 'series',
			options: RecordingRuleOptions,
		) => Promise<void> | void;
		onCancelRule?: (ruleId: string) => Promise<void> | void;
		onToggleFavorite?: (channelNumber: string) => Promise<void> | void;
		allowPopout?: boolean;
		onPopout?: () => void;
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
		onRecordEpisode,
		onRecordSeries,
		onUpdateRule,
		onCancelRule,
		onToggleFavorite,
	}: Props = $props();

	const DETAIL_POLL_INTERVAL_MS = 5_000;
	const CAPTION_POLL_INTERVAL_MS = 1_000;

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

	let videoInfo = $state<{
		codec: string | null;
		width: number | null;
		height: number | null;
		fps: number | null;
	} | null>(null);
	let audioTracks = $state<HDHomeRunRecordingAudioInfo[]>([]);
	let hasCaptions = $state(false);
	let secondaryCaptions = $state<'unknown' | 'available' | 'unavailable' | null>(null);
	let currentCaptionTrack = $state<1 | 2>(1);
	let currentAudioIndex = $state<number | null>(null);
	let captionsEnabled = $state(false);
	let thumbnailsAvailable = $state(false);
	let thumbnailCues = $state<ThumbnailCue[]>([]);
	let thumbSpriteUrl = $state('');

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
	let syncPlayRoom = $state<SyncPlayRoom | null>(null);
	let syncPlayStatus = $state<SyncPlayStatus>('disconnected');
	let syncPlayPingMs = $state(0);

	let centerFlash = $state<'play' | 'pause' | null>(null);
	let centerFlashTimer: ReturnType<typeof setTimeout> | undefined;

	let internalRecordingLoading = $state(false);
	let isVideoLoading = $state(true);
	let errorMessage = $state<string | null>(null);
	let errorDetail = $state<string | null>(null);
	let destroyed = false;
	let detailPollHandle: ReturnType<typeof setInterval> | undefined;
	let captionPollHandle: ReturnType<typeof setInterval> | undefined;
	let captionsPollInFlight = false;
	let airplayAvailable = $state(false);
	let airplaySessionId: string | null = null;
	let airplayResumeFrom = 0;

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
			if (currentAudioIndex === null && detail.audio.length > 0) {
				currentAudioIndex = 0;
			}
			hasCaptions = detail.has_captions;
			secondaryCaptions = detail.secondary_captions;
			transcodeInfo = detail.transcode;
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

	function seekTo(targetSeconds: number) {
		if (!seekable || !videoElement) return;
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
			} catch {}
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
			} catch {}
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

	function handleToggleFavorite() {
		if (channelNumber && onToggleFavorite) {
			onToggleFavorite(channelNumber);
		}
		resetAutoHideTimer();
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
			showSyncPlayModal;

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
		const target = e.target as HTMLElement | null;
		if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
			if (e.key === 'Escape') {
				(target as HTMLElement).blur();
			}
			return;
		}

		resetAutoHideTimer();
		if (e.key === 'Escape') {
			if (showSyncPlayModal) {
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

	async function handleRecordEpisode(options?: RecordingRuleOptions) {
		showRecordMenu = false;
		showOptionsDialog = false;
		internalRecordingLoading = true;
		const effectiveOptions: RecordingRuleOptions = {
			title: effectiveAiring?.title ?? channelName,
			...options,
		};
		const targetChannel = effectiveOptions.channel !== undefined ? effectiveOptions.channel : channelNumber;
		try {
			if (isWatchSession && watchSessionId) {
				await api.promoteWatch(watchSessionId, {
					title: effectiveAiring?.title ?? channelName,
					episode_title: effectiveAiring?.episode_title ?? undefined,
				});
				return;
			}
			if (onRecordEpisode) {
				await onRecordEpisode(
					effectiveAiring?.series_id,
					targetChannel,
					effectiveAiring?.start,
					effectiveOptions,
				);
			} else {
				const updatedRules = await api.addHDHomeRunRecordingRule({
					series_id: effectiveAiring?.series_id || 'auto',
					channel: targetChannel,
					date_time: effectiveAiring?.start ?? undefined,
					title: effectiveOptions.title,
					start_padding: effectiveOptions.startPadding,
					end_padding: effectiveOptions.endPadding,
					recent_only: effectiveOptions.recentOnly,
					max_episodes_to_keep: effectiveOptions.maxEpisodesToKeep,
					server: effectiveOptions.server,
				});
				if (Array.isArray(updatedRules)) {
					recordingRules = updatedRules;
				}
			}
		} catch (err) {
			errorMessage = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			internalRecordingLoading = false;
		}
	}

	async function handleRecordSeries(options?: RecordingRuleOptions) {
		showRecordMenu = false;
		showOptionsDialog = false;
		internalRecordingLoading = true;
		const effectiveOptions: RecordingRuleOptions = {
			title: effectiveAiring?.title ?? channelName,
			...options,
		};
		const seriesId = effectiveAiring?.series_id || 'auto';
		const targetChannel = effectiveOptions.channel !== undefined ? effectiveOptions.channel : channelNumber;
		try {
			if (isWatchSession && watchSessionId) {
				await api.promoteWatch(watchSessionId, {
					title: effectiveAiring?.title ?? channelName,
					episode_title: effectiveAiring?.episode_title ?? undefined,
				});
			}
			if (onRecordSeries) {
				await onRecordSeries(seriesId, targetChannel, effectiveOptions);
			} else {
				const updatedRules = await api.addHDHomeRunRecordingRule({
					series_id: seriesId,
					channel: targetChannel,
					title: effectiveOptions.title,
					title_match_mode: effectiveOptions.titleMatchMode,
					keyword_query: effectiveOptions.keywordQuery,
					start_padding: effectiveOptions.startPadding,
					end_padding: effectiveOptions.endPadding,
					recent_only: effectiveOptions.recentOnly,
					max_episodes_to_keep: effectiveOptions.maxEpisodesToKeep,
					server: effectiveOptions.server,
				});
				if (Array.isArray(updatedRules)) {
					recordingRules = updatedRules;
				}
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

	async function handleUpdateRule(ruleId: string, mode: 'episode' | 'series', options: RecordingRuleOptions) {
		showRecordMenu = false;
		showOptionsDialog = false;
		internalRecordingLoading = true;
		try {
			if (onUpdateRule) {
				await onUpdateRule(ruleId, mode, options);
			} else {
				await api.updateHDHomeRunRecordingRule(ruleId, {
					channel: options.channel,
					title: options.title,
					title_match_mode: options.titleMatchMode,
					keyword_query: options.keywordQuery,
					start_padding: options.startPadding,
					end_padding: options.endPadding,
					recent_only: options.recentOnly,
					max_episodes_to_keep: options.maxEpisodesToKeep,
				});
			}
		} catch (err) {
			errorMessage = err instanceof Error && err.message ? err.message : get(_)('common.connection_save_error');
		} finally {
			internalRecordingLoading = false;
		}
	}

	function handleConfirmOptions(mode: 'episode' | 'series', options: RecordingRuleOptions) {
		if (currentRule) {
			handleUpdateRule(currentRule.RecordingRuleID, mode, options);
			return;
		}
		if (mode === 'series') {
			handleRecordSeries(options);
		} else {
			handleRecordEpisode(options);
		}
	}

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
		const handleWaiting = () => { isVideoLoading = true; };
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
				if (autoHideTimer) clearTimeout(autoHideTimer);
				if (centerFlashTimer) clearTimeout(centerFlashTimer);
				mpegtsPlayer.teardownPlayer();
				if (airplaySessionId) {
					api.stopHlsSession(airplaySessionId);
					airplaySessionId = null;
				}
				videoElement = null;
				captionController.teardown();
				captionCues = [];
			},
		};
	}

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

	// AirPlay Setup
	$effect(() => {
		const video = videoElement as (HTMLVideoElement & { webkitShowPlaybackTargetPicker?: () => void }) | null;
		const hasAirplay =
			typeof window !== 'undefined' &&
			('WebKitPlaybackTargetAvailabilityEvent' in window ||
				'WebKitPlaybackTargetAvailabilityEvent' in (globalThis as unknown as Record<string, unknown>));

		if (!video || !hasAirplay) return;

		// Swapping to the real for_cast HLS URL as soon as a route becomes
		// available - not deferred until the route actually connects - is
		// required, not just an optimization: confirmed against real
		// Safari/Apple TV hardware, WebKit negotiates an AirPlay connection as
		// audio-only (remote-control works, sound-waves "Now Playing" icon
		// shows, but no picture ever reaches the TV) whenever the video's src
		// was still the mpegts.js MSE blob: URL at the moment the route was
		// picked - swapping the src afterwards doesn't upgrade an
		// already-negotiated audio-only session to video. The video element
		// has to already be on a directly-fetchable HTTP(S) URL *before* the
		// picker ever opens, which - combined with webkitShowPlaybackTargetPicker()
		// needing to fire with no await ahead of it (see showAirPlayPicker
		// below) - means the swap can't be triggered by the click at all. So
		// it happens here instead, the moment a nearby route is discovered:
		// by the time the user actually clicks, the video is already playing
		// from a URL an Apple TV can pull directly, whether they click at all
		// or (per real hardware) Safari auto-reconnects a previously-picked
		// route on its own.
		const handleAvailabilityChange = (event: Event) => {
			airplayAvailable = (event as unknown as { availability: string }).availability === 'available';
			if (airplayAvailable) {
				startAirPlayPlayback();
			} else {
				stopAirPlayPlayback();
			}
		};

		video.addEventListener('webkitplaybacktargetavailabilitychanged', handleAvailabilityChange);
		return () => {
			video.removeEventListener('webkitplaybacktargetavailabilitychanged', handleAvailabilityChange);
		};
	});

	// By the time this runs, the video is already on the for_cast HLS URL
	// (swapped in reactively as soon as the route became available - see
	// handleAvailabilityChange above), so all this needs to do is open the
	// native picker. Must stay synchronous, with nothing awaited first -
	// Safari only honors webkitShowPlaybackTargetPicker() while the click's
	// transient user activation is still live, the same constraint Chrome's
	// Cast picker has (see requestCastSession() in cast-loader.ts).
	function showAirPlayPicker() {
		(videoElement as (HTMLVideoElement & { webkitShowPlaybackTargetPicker?: () => void }) | null)
			?.webkitShowPlaybackTargetPicker?.();
	}

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

	// AirPlay DOES need to reuse the same for_cast/token session Google Cast
	// uses (not a cookie-authenticated one): once a route actually connects,
	// it's the Apple TV itself - a separate device on the LAN - that fetches
	// the playlist/segments directly, exactly like a Chromecast receiver, and
	// it has no way to send this browser's session cookie. A cookie-only
	// session 404s/401s on the TV's own fetch (the "can't play" no-entry icon
	// on real hardware).
	//
	// That token route's wildcard Access-Control-Allow-Origin is only a
	// problem for *this* page's own <video> element, which - before/unless a
	// route actually connects - may itself try to load the swapped src
	// locally. With crossorigin="use-credentials" still set (needed for the
	// normal cookie-authenticated src), that local fetch sends credentials,
	// and wildcard-origin + credentialed-request is forbidden by the CORS
	// spec (confirmed via a real Safari console error). So the crossorigin
	// attribute is dropped for the duration of the swap - the token in the
	// URL is this route's actual auth, cookies were never required for it -
	// and restored once AirPlay ends and normal cookie-authenticated
	// playback resumes below.
	async function startAirPlayPlayback() {
		if (!videoElement || airplaySessionId) return;
		try {
			airplayResumeFrom = seekable ? baseOffsetSeconds + videoCurrentTime : 0;
			const { url, sessionId } = await buildCastContentUrl();
			if (!videoElement || destroyed || !airplayAvailable) {
				api.stopHlsSession(sessionId);
				return;
			}
			airplaySessionId = sessionId;
			mpegtsPlayer.teardownPlayer();
			videoElement.removeAttribute('crossorigin');
			videoElement.src = url;
			videoElement.load();
			safePlay();
		} catch {
			// ignore
		}
	}

	function stopAirPlayPlayback() {
		if (!airplaySessionId) return;
		api.stopHlsSession(airplaySessionId);
		airplaySessionId = null;
		if (!videoElement || destroyed) return;
		videoElement.setAttribute('crossorigin', 'use-credentials');
		videoElement.removeAttribute('src');
		videoElement.load();
		if (seekable) {
			const resumeAt = airplayResumeFrom + videoElement.currentTime;
			baseOffsetSeconds = resumeAt;
			videoCurrentTime = 0;
			captionController.resetStretchCursor();
			captionController.refreshCaptionCues();
			mpegtsPlayer.createPlayerAt(videoElement, buildStreamUrl(resumeAt, currentAudioIndex));
		} else {
			mpegtsPlayer.createPlayerAt(videoElement, src);
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
	class="overlay"
	class:hide-cursor={!showControls && !videoPaused}
	role="dialog"
	aria-label={title}
	tabindex="-1"
	bind:this={overlayEl}
	onmousemove={handleMouseMove}
	use:portal
>
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

	<!-- Video Area -->
	<div
		class="video-container"
		class:aspect-16-9={aspectRatio === '16:9'}
		class:aspect-4-3={aspectRatio === '4:3'}
		onclick={togglePlay}
		ondblclick={toggleFullscreen}
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

		<!-- Loading Quip & Spinner Overlay -->
		<LoadingQuipOverlay visible={isVideoLoading && !errorMessage} />
	</div>

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
			bind:showAudioMenu
			bind:showSettingsMenu
			onSeek={seekTo}
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
			syncPlayActive={Boolean(syncPlayRoom)}
			syncPlayParticipantsCount={syncPlayRoom?.participants?.length ?? 0}
			onToggleSyncPlay={() => (showSyncPlayModal = !showSyncPlayModal)}
			onTogglePlaybackInfo={() => (showPlaybackInfo = !showPlaybackInfo)}
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
					{#if isInProgress && !videoInfo && audioTracks.length === 0}
						<div class="info-row">
							<span class="value">{$_('player.analyzing_stream', { default: 'Analyzing stream…' })}</span>
						</div>
					{/if}
					{#if videoInfo}
						<div class="info-section-heading">{$_('player.video', { default: 'Video' })}</div>
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
