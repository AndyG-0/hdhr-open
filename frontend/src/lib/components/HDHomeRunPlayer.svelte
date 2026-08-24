<script lang="ts">
	import type Mpegts from 'mpegts.js';
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
	import HDHomeRunRecordingOptionsDialog from './details/HDHomeRunRecordingOptionsDialog.svelte';

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

	interface ThumbnailCue {
		startSeconds: number;
		endSeconds: number;
		x: number;
		y: number;
		w: number;
		h: number;
	}

	const DETAIL_POLL_INTERVAL_MS = 5_000;
	const CAPTION_POLL_INTERVAL_MS = 1_000;
	// How far the video↔caption offset can drift before it's worth
	// correcting - avoids re-timing every cue over ordinary network jitter
	// in the /recording-detail round trip.
	const RESYNC_DRIFT_THRESHOLD_SECONDS = 1.5;
	// Live extraction (segment decode + poll interval) routinely delivers a
	// cue 10-15s after the dialogue it transcribes - well past that cue's own
	// few-second [start, end] window relative to live playback. A cue that
	// arrives already-expired would never satisfy the browser's native
	// "currentTime is inside this cue" activation check, so it would just
	// silently never render. Stretching such a cue's end to start from
	// whenever it actually arrives keeps it on screen for a bit instead.
	const LIVE_CUE_MIN_DISPLAY_SECONDS = 4;

	let player: ReturnType<typeof Mpegts.createPlayer> | undefined;
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

	interface CaptionCue {
		start: number;
		end: number;
		text: string;
		// Set once, only when this cue first arrives already past its natural
		// end (see LIVE_CUE_MIN_DISPLAY_SECONDS) - the stretched window it was
		// given, in the same absolute (capture-start-relative) basis as
		// start/end so it survives baseOffsetSeconds changing on a later
		// resync instead of being re-decided (and re-triggered) against
		// whatever currentTime happens to be at rebuild time.
		displayStart?: number;
		displayEnd?: number;
	}
	// Captions are extracted once for the whole recording, so their cue
	// timestamps are absolute (0 = start of the recording). But each seek
	// tears down and recreates the mpegts player against a freshly
	// `-ss`-seeked ffmpeg stream, which resets the video element's own
	// currentTime back to 0 - so the native VTT cue times would only ever
	// line up with playback when baseOffsetSeconds is 0. A plain
	// `<track src>` can't be re-timed after the browser parses it, so
	// cues are parsed here and re-added to a managed TextTrack, shifted by
	// -baseOffsetSeconds, every time the playback origin changes.
	// Plain (not $state) - a live TextTrack is a mutable host object, and
	// wrapping it in Svelte's deep-reactivity proxy makes every cues
	// add/remove inside refreshCaptionCues() itself trip the reactivity
	// that's supposed to call refreshCaptionCues(), which loops forever.
	// It's refreshed imperatively at every call site that can affect it
	// instead (see ensureCaptionTrack/seekTo/toggleCaptions).
	let captionCues = $state<CaptionCue[]>([]);
	let capTextTrack: TextTrack | null = null;
	// Absolute (capture-start-relative) seconds - the earliest a not-yet-decided
	// stretched cue is allowed to start. Advanced past each stretched cue's
	// displayEnd as it's assigned so a burst of several already-stale cues
	// arriving in the same poll get staggered one after another instead of
	// all piling up on screen from `now` at once.
	let nextStretchSlotAbsolute = 0;

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

	const currentRule = $derived.by(() => {
		if (!recordingRules || recordingRules.length === 0) return null;
		const chNum = channelNumber;
		const air = effectiveAiring;
		return (
			recordingRules.find((r) => {
				const channelMatches = !r.ChannelOnly || (chNum && r.ChannelOnly.split('|').includes(chNum));
				if (!channelMatches) return false;
				if (r.DateTimeOnly != null && air?.start != null) {
					return Math.abs(r.DateTimeOnly - air.start) < 60;
				}
				return !!(r.SeriesID && air?.series_id && r.SeriesID === air.series_id);
			}) ?? null
		);
	});

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

	function genericHint() {
		return get(_)('hdhomerun.detail.playback_failed_hint', {
			values: { action: get(_)('hdhomerun.detail.open_external') },
		});
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

	function parseThumbnailVtt(text: string): ThumbnailCue[] {
		const cues: ThumbnailCue[] = [];
		const timeToSeconds = (ts: string): number => {
			const match = ts.match(/(\d+):(\d+):(\d+(?:\.\d+)?)/);
			if (!match) return 0;
			return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
		};
		const blocks = text.split(/\r?\n\r?\n/);
		for (const block of blocks) {
			const lines = block.split(/\r?\n/).filter((l) => l.trim());
			const cueLine = lines.find((l) => l.includes('-->'));
			const xywhLine = lines.find((l) => l.includes('#xywh='));
			if (!cueLine || !xywhLine) continue;
			const [startRaw, endRaw] = cueLine.split('-->').map((s) => s.trim());
			const xywhMatch = xywhLine.match(/#xywh=(\d+),(\d+),(\d+),(\d+)/);
			if (!xywhMatch) continue;
			cues.push({
				startSeconds: timeToSeconds(startRaw),
				endSeconds: timeToSeconds(endRaw),
				x: Number(xywhMatch[1]),
				y: Number(xywhMatch[2]),
				w: Number(xywhMatch[3]),
				h: Number(xywhMatch[4]),
			});
		}
		return cues;
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

	function parseVttTimestamp(raw: string): number {
		const parts = raw.trim().split(':');
		if (parts.length === 3) {
			return Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2]);
		} else if (parts.length === 2) {
			return Number(parts[0]) * 60 + Number(parts[1]);
		} else if (parts.length === 1) {
			return Number(parts[0]) || 0;
		}
		return 0;
	}

	function parseCaptionsVtt(text: string): CaptionCue[] {
		const cues: CaptionCue[] = [];
		const blocks = text.replace(/\r\n/g, '\n').split(/\n\n+/);
		for (const block of blocks) {
			const lines = block.split('\n').filter((l) => l.length > 0);
			const cueLineIndex = lines.findIndex((l) => l.includes('-->'));
			if (cueLineIndex === -1) continue;
			const [startRaw, endRaw] = lines[cueLineIndex].split('-->');
			const start = parseVttTimestamp(startRaw);
			const end = parseVttTimestamp(endRaw.trim().split(/\s+/)[0]);
			const textLines = lines.slice(cueLineIndex + 1);
			if (textLines.length === 0) continue;
			// ffmpeg's CEA-608 decoder writes the literal two characters "\h"
			// for a caption-positioning space code (used for indentation)
			// instead of an actual space - a run of "\h\h\h\h" is just
			// indentation that never got converted to real whitespace, so
			// swap it for a real space so it reads as normal text instead of
			// showing the literal escape code. Also strip any WebVTT tags.
			const cleanedText = textLines
				.join('\n')
				.replace(/\\h/g, ' ')
				.replace(/<[^>]+>/g, '');
			if (!cleanedText.trim()) continue;
			cues.push({ start, end, text: cleanedText });
		}
		return cues;
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

	function ensureCaptionTrack() {
		if (capTextTrack || !videoElement) return;
		capTextTrack = videoElement.addTextTrack('subtitles', 'Captions', 'en');
		capTextTrack.mode = captionsEnabled ? 'showing' : 'hidden';
	}

	// `allowStretch` is only true for cues genuinely new to this session
	// (pollLiveCaptions). refreshCaptionCues() re-renders the *entire*
	// captionCues history on every resync/seek - deciding stretch there too
	// would flag every already-expired cue ever received (i.e. nearly all of
	// history) as "just arrived", flooding the screen with the whole
	// transcript at once. Cues that were already stretched keep that decision
	// via displayStart/displayEnd regardless of which path re-renders them.
	function appendCaptionCues(cues: CaptionCue[], { allowStretch = false }: { allowStretch?: boolean } = {}) {
		if (!capTextTrack) return;
		for (const cue of cues) {
			if (allowStretch && isInProgress && videoElement && cue.displayEnd === undefined) {
				const naturalEnd = cue.end - baseOffsetSeconds;
				// See LIVE_CUE_MIN_DISPLAY_SECONDS: while live, a cue that's
				// already past its natural end by the time it arrives gets held
				// on screen for a bit instead of being dropped as stale.
				if (naturalEnd <= videoElement.currentTime) {
					const nowAbsolute = baseOffsetSeconds + videoElement.currentTime;
					const slotStart = Math.max(cue.start, nextStretchSlotAbsolute, nowAbsolute);
					cue.displayStart = slotStart;
					cue.displayEnd = slotStart + LIVE_CUE_MIN_DISPLAY_SECONDS;
					nextStretchSlotAbsolute = cue.displayEnd;
				}
			}
			const start = (cue.displayStart ?? cue.start) - baseOffsetSeconds;
			const end = (cue.displayEnd ?? cue.end) - baseOffsetSeconds;
			if (end <= 0) continue;
			try {
				capTextTrack.addCue(new VTTCue(Math.max(0, start), end, cue.text));
			} catch {
				// A malformed cue shouldn't take down the rest of the track.
			}
		}
	}

	function refreshCaptionCues() {
		if (!capTextTrack) return;
		while (capTextTrack.cues && capTextTrack.cues.length > 0) {
			capTextTrack.removeCue(capTextTrack.cues[0]);
		}
		appendCaptionCues(captionCues);
	}

	async function loadCaptions(): Promise<void> {
		if (!seekable || !captionsUrl) return;
		try {
			const response = await fetch(captionsUrl, { credentials: 'include' });
			if (!response.ok) return;
			const text = await response.text();
			const cues = parseCaptionsVtt(text);
			if (cues.length === 0) return;
			captionCues = cues;
			if (!hasCaptions) {
				hasCaptions = true;
			}
			ensureCaptionTrack();
			refreshCaptionCues();
		} catch {
			// No captions: the CC button stays visible per hasCaptions, but
			// toggling it just won't show anything.
		}
	}

	// While live, the server's .live.vtt grows in place - it's strictly
	// append-only and already de-duplicated server-side - so rather than
	// loadCaptions()'s wholesale replace-and-rebuild, only the cues beyond
	// what we've already parsed (captionCues.length, which doubles as the
	// cursor) get appended directly to the TextTrack. A seek doesn't reset
	// this: it calls refreshCaptionCues() to re-render the same captionCues
	// against the new baseOffsetSeconds, so the length-based cursor still
	// lines up with what's actually in the track afterward.
	async function pollLiveCaptions(): Promise<void> {
		if (!seekable || !captionsUrl) return;
		try {
			const response = await fetch(captionsUrl, { credentials: 'include' });
			if (!response.ok) return;
			const text = await response.text();
			const cues = parseCaptionsVtt(text);
			if (cues.length > 0 && !hasCaptions) {
				hasCaptions = true;
			}
			if (cues.length <= captionCues.length) return;
			const newCues = cues.slice(captionCues.length);
			captionCues = cues;
			ensureCaptionTrack();
			appendCaptionCues(newCues, { allowStretch: true });
		} catch {
			// Live captions are a best-effort enhancement; a failed poll just
			// means the client tries again on the next interval.
		}
	}

	function findCueAt(seconds: number): ThumbnailCue | null {
		if (thumbnailCues.length === 0) return null;
		let found = thumbnailCues[0];
		for (const cue of thumbnailCues) {
			if (cue.startSeconds > seconds) break;
			found = cue;
		}
		return found;
	}

	// baseOffsetSeconds is set once at attach from a /recording-detail
	// snapshot taken before the stream has even started producing frames, so
	// it's off by however long stream spin-up takes - and with nothing to
	// correct it afterward, that error (plus any longer-session drift) would
	// otherwise stick around for the rest of the live view. duration (wall
	// clock elapsed since capture start, refreshed every detail poll) and
	// videoCurrentTime (the real, accurate playback position) are on a
	// shared clock, so duration - videoCurrentTime is always a sound
	// estimate of what baseOffsetSeconds should currently be - this just
	// re-checks it on every poll and nudges it back in line if it's drifted.
	function maybeResyncBaseOffset() {
		if (!isInProgress || duration === null || !videoElement) return;
		// currentTime freezes while paused but duration keeps advancing, so
		// resyncing here would push the offset forward for no playback
		// progress. videoCurrentTime === 0 also covers the moment right
		// after a manual seekTo() resets it, before playback has resumed.
		if (videoElement.paused || videoCurrentTime <= 0) return;
		const candidate = Math.max(0, duration - videoCurrentTime);
		if (Math.abs(candidate - baseOffsetSeconds) > RESYNC_DRIFT_THRESHOLD_SECONDS) {
			baseOffsetSeconds = candidate;
			refreshCaptionCues();
		}
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
			maybeResyncBaseOffset();
			if (wasInProgress && !isInProgress) {
				stopPolling();
				stopCaptionPolling();
				loadThumbnails();
				loadCaptions();
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
				await pollLiveCaptions();
			} finally {
				captionsPollInFlight = false;
			}
		}, CAPTION_POLL_INTERVAL_MS);
	}

	// mpegts.js reports a failed stream request as a bare "network error" and
	// throws the response body away, so the backend's carefully built 502
	// detail — which names the actual ffmpeg failure — never reaches the
	// user. Re-requesting the same URL is the only way to read it, and it's
	// cheap: the request has already failed, and the backend fails the same
	// way again in well under a second.
	async function fetchServerDetail(url: string) {
		try {
			const response = await fetch(url, { credentials: 'include' });
			if (response.ok) {
				response.body?.cancel();
				return null;
			}
			const body = await response.json();
			return typeof body?.detail === 'string' ? body.detail : null;
		} catch {
			return null;
		}
	}

	function teardownPlayer() {
		player?.pause();
		player?.unload();
		player?.detachMediaElement();
		player?.destroy();
		player = undefined;
	}

	function createPlayerAt(node: HTMLVideoElement, url: string) {
		errorMessage = null;
		errorDetail = null;
		// mpegts.js's UMD bundle references `window` at import time, so a
		// static import would crash SvelteKit's server-side render of this
		// page (Node has no `window`). Deferring to a dynamic import here
		// means it only ever loads client-side, once this action runs.
		import('mpegts.js').then(({ default: mpegts }) => {
			if (destroyed) return;
			player = mpegts.createPlayer(
				{ type: 'mse', isLive: true, url, withCredentials: true },
				// liveBufferLatencyChasing auto-seeks forward whenever the playhead
				// falls behind the live edge — which is exactly what a manual
				// buffer-rewind (see rewind()/fastForward() below) does, so leaving
				// it on snaps the video straight back to live the instant you
				// scrub backward. Off, so a manual seek stays where you put it.
				{ enableStashBuffer: false, liveBufferLatencyChasing: false },
			);
			player.on(mpegts.Events.ERROR, (errorType: string) => {
				errorMessage = genericHint();
				if (errorType !== mpegts.ErrorTypes.NETWORK_ERROR) return;
				fetchServerDetail(url).then((detail) => {
					if (!destroyed) errorDetail = detail;
				});
			});
			player.attachMediaElement(node);
			player.load();
			player.play();
		});
	}

	function seekTo(targetSeconds: number) {
		if (!seekable || !videoElement) return;
		let clamped = Math.max(0, targetSeconds);
		if (duration !== null) clamped = Math.min(clamped, duration);
		teardownPlayer();
		baseOffsetSeconds = clamped;
		videoCurrentTime = 0;
		// A stale slot from before the seek is on the old absolute clock and
		// could push a freshly-stretched cue arbitrarily far into the future
		// relative to the new origin.
		nextStretchSlotAbsolute = 0;
		refreshCaptionCues();
		createPlayerAt(videoElement, buildStreamUrl(clamped, currentAudioIndex));
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
		ensureCaptionTrack();
		if (capTextTrack) capTextTrack.mode = captionsEnabled ? 'showing' : 'hidden';
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
					createPlayerAt(node, buildStreamUrl(undefined, currentAudioIndex));
					pollLiveCaptions();
					startPolling();
					startCaptionPolling();
				} else {
					baseOffsetSeconds = 0;
					createPlayerAt(node, buildStreamUrl(0, currentAudioIndex));
					loadThumbnails();
					loadCaptions();
				}
			} else {
				createPlayerAt(node, src);
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
				teardownPlayer();
				videoElement = null;
				capTextTrack = null;
				captionCues = [];
				nextStretchSlotAbsolute = 0;
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
				<div class="menu-popover-wrap">
					<button
						class="control-btn record-btn"
						class:active={showRecordMenu}
						class:recording={currentRule !== null}
						onclick={() => (showRecordMenu = !showRecordMenu)}
						disabled={isActionLoading}
						aria-label={currentRule ? $_('player.recording_active') : $_('player.record')}
						title={currentRule ? $_('player.recording_active') : $_('player.record')}
					>
						<span class="record-dot" class:pulsing={isPending}></span>
						{#if currentRule}
							{$_('player.recording_active')}
						{:else}
							{$_('player.record')}
						{/if}
					</button>
					{#if showRecordMenu}
						<div class="popover-menu record-popover">
							<div class="menu-header">
								{effectiveAiring?.title ?? channelName}
							</div>
							<div class="menu-items">
								{#if currentRule}
									{#if isPending}
										<div class="pending-hint">{$_('player.pending_confirmation')}</div>
									{/if}
									<button
										class="menu-item danger"
										disabled={isActionLoading}
										onclick={handleCancelRecording}
									>
										{$_('player.cancel_recording')}
									</button>
								{:else}
									<button
										class="menu-item"
										disabled={isActionLoading}
										onclick={() => handleRecordEpisode()}
									>
										🔴 {$_('player.record_episode')}
									</button>
									{#if effectiveAiring?.series_id}
										<button
											class="menu-item"
											disabled={isActionLoading}
											onclick={() => handleRecordSeries()}
										>
											{$_('player.record_series')}
										</button>
									{/if}
									<button
										class="menu-item"
										disabled={isActionLoading}
										onclick={() => {
											showRecordMenu = false;
											showOptionsDialog = true;
										}}
									>
										⚙️ {$_('player.recording_options')}
									</button>
								{/if}
							</div>
						</div>
					{/if}
				</div>
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

	{#if showOptionsDialog && effectiveAiring}
		<HDHomeRunRecordingOptionsDialog
			airing={effectiveAiring}
			channelName={channelName}
			canRecordSeries={Boolean(effectiveAiring.series_id)}
			{officialDvrActive}
			loading={isActionLoading}
			onConfirm={handleConfirmOptions}
			onClose={() => (showOptionsDialog = false)}
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

	/* Browser default cue styling sizes text relative to the video element's
	   own dimensions, which reads as oversized on a large player - pin it to
	   a fixed, readable size instead. */
	.video::cue {
		font-size: 1.05rem;
		line-height: 1.4;
		background-color: rgba(0, 0, 0, 0.75);
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

	.record-btn {
		position: relative;
	}

	.record-btn.recording {
		background: rgba(224, 90, 90, 0.25);
		border-color: rgba(224, 90, 90, 0.6);
		color: #ffb4b4;
	}

	.record-btn.recording:hover {
		background: rgba(224, 90, 90, 0.35);
	}

	.record-dot {
		display: inline-block;
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 50%;
		background: #ff5555;
	}

	.record-dot.pulsing {
		animation: record-pulse 1.5s infinite;
	}

	@keyframes record-pulse {
		0%,
		100% {
			opacity: 1;
			transform: scale(1);
		}
		50% {
			opacity: 0.4;
			transform: scale(0.85);
		}
	}

	.record-popover {
		width: 14rem;
	}

	.menu-item.danger {
		color: #ff8888;
	}

	.menu-item.danger:hover {
		background: rgba(224, 90, 90, 0.2);
		color: #ffb4b4;
	}

	.pending-hint {
		padding: 0.35rem 0.75rem;
		font-size: 0.75rem;
		color: #eab308;
		font-style: italic;
	}
</style>
