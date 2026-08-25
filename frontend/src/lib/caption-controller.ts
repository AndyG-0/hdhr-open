import { parseCaptionsVtt, type CaptionCue } from './vtt-parser';

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

interface CaptionControllerOptions {
	getVideoElement: () => HTMLVideoElement | null;
	getCaptionsUrl: () => string;
	getSeekable: () => boolean | undefined;
	getCaptionsEnabled: () => boolean;
	getIsInProgress: () => boolean;
	getDuration: () => number | null;
	getVideoCurrentTime: () => number;
	getCaptionCues: () => CaptionCue[];
	setCaptionCues: (cues: CaptionCue[]) => void;
	getHasCaptions: () => boolean;
	setHasCaptions: (value: boolean) => void;
	getBaseOffsetSeconds: () => number;
	setBaseOffsetSeconds: (value: number) => void;
}

// Encapsulates caption-track lifecycle (VTT fetch/parse, native TextTrack
// management, live-cue stretching) and the live-delay baseOffsetSeconds
// resync that keeps cue timing lined up with playback. All reactive state
// it reads or writes lives in the owning component and is threaded through
// via the getter/setter options above - only the caption track handle and
// the live-cue stretch cursor are private to this controller.
export function createCaptionController(options: CaptionControllerOptions) {
	// Plain (not $state) - a live TextTrack is a mutable host object, and
	// wrapping it in Svelte's deep-reactivity proxy makes every cues
	// add/remove inside refreshCaptionCues() itself trip the reactivity
	// that's supposed to call refreshCaptionCues(), which loops forever.
	// It's refreshed imperatively at every call site that can affect it
	// instead (see ensureCaptionTrack/seekTo/toggleCaptions).
	let capTextTrack: TextTrack | null = null;
	// Absolute (capture-start-relative) seconds - the earliest a not-yet-decided
	// stretched cue is allowed to start. Advanced past each stretched cue's
	// displayEnd as it's assigned so a burst of several already-stale cues
	// arriving in the same poll get staggered one after another instead of
	// all piling up on screen from `now` at once.
	let nextStretchSlotAbsolute = 0;

	function ensureCaptionTrack() {
		const videoElement = options.getVideoElement();
		if (capTextTrack || !videoElement) return;
		capTextTrack = videoElement.addTextTrack('subtitles', 'Captions', 'en');
		capTextTrack.mode = options.getCaptionsEnabled() ? 'showing' : 'hidden';
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
		const videoElement = options.getVideoElement();
		const isInProgress = options.getIsInProgress();
		const baseOffsetSeconds = options.getBaseOffsetSeconds();
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
		appendCaptionCues(options.getCaptionCues());
	}

	async function loadCaptions(): Promise<void> {
		if (!options.getSeekable() || !options.getCaptionsUrl()) return;
		try {
			const response = await fetch(options.getCaptionsUrl(), { credentials: 'include' });
			if (!response.ok) return;
			const text = await response.text();
			const cues = parseCaptionsVtt(text);
			if (cues.length === 0) return;
			options.setCaptionCues(cues);
			if (!options.getHasCaptions()) {
				options.setHasCaptions(true);
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
		if (!options.getSeekable() || !options.getCaptionsUrl()) return;
		try {
			const response = await fetch(options.getCaptionsUrl(), { credentials: 'include' });
			if (!response.ok) return;
			const text = await response.text();
			const cues = parseCaptionsVtt(text);
			if (cues.length > 0 && !options.getHasCaptions()) {
				options.setHasCaptions(true);
			}
			const existingCues = options.getCaptionCues();
			if (cues.length <= existingCues.length) return;
			const newCues = cues.slice(existingCues.length);
			options.setCaptionCues(cues);
			ensureCaptionTrack();
			appendCaptionCues(newCues, { allowStretch: true });
		} catch {
			// Live captions are a best-effort enhancement; a failed poll just
			// means the client tries again on the next interval.
		}
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
		const isInProgress = options.getIsInProgress();
		const duration = options.getDuration();
		const videoElement = options.getVideoElement();
		if (!isInProgress || duration === null || !videoElement) return;
		// currentTime freezes while paused but duration keeps advancing, so
		// resyncing here would push the offset forward for no playback
		// progress. videoCurrentTime === 0 also covers the moment right
		// after a manual seekTo() resets it, before playback has resumed.
		const videoCurrentTime = options.getVideoCurrentTime();
		if (videoElement.paused || videoCurrentTime <= 0) return;
		const candidate = Math.max(0, duration - videoCurrentTime);
		const baseOffsetSeconds = options.getBaseOffsetSeconds();
		if (Math.abs(candidate - baseOffsetSeconds) > RESYNC_DRIFT_THRESHOLD_SECONDS) {
			options.setBaseOffsetSeconds(candidate);
			refreshCaptionCues();
		}
	}

	function setMode(showing: boolean) {
		if (capTextTrack) capTextTrack.mode = showing ? 'showing' : 'hidden';
	}

	// A stale slot from before a seek is on the old absolute clock and
	// could push a freshly-stretched cue arbitrarily far into the future
	// relative to the new origin.
	function resetStretchCursor() {
		nextStretchSlotAbsolute = 0;
	}

	function teardown() {
		capTextTrack = null;
		nextStretchSlotAbsolute = 0;
	}

	return {
		ensureCaptionTrack,
		refreshCaptionCues,
		loadCaptions,
		pollLiveCaptions,
		maybeResyncBaseOffset,
		setMode,
		resetStretchCursor,
		teardown,
	};
}
