import { parseCaptionsVtt, type CaptionCue } from './vtt-parser';

// How far the video↔caption offset can drift before it's worth
// correcting - avoids re-timing every cue over ordinary network jitter
// in the /recording-detail round trip.
const RESYNC_DRIFT_THRESHOLD_SECONDS = 1.5;
// Live extraction (segment decode + poll interval) routinely delivers a
// cue after the dialogue it transcribes - well past that cue's own
// few-second [start, end] window relative to live playback. A cue that
// arrives already-expired would never satisfy the browser's native
// "currentTime is inside this cue" activation check, so it would just
// silently never render. Stretching such a cue's end to start from
// whenever it actually arrives keeps it on screen for a bit instead.
//
// Duration and simultaneous-line count are chosen to match live
// closed-captioning industry practice (Netflix/BBC/FCC guidance, plus
// Smashing Magazine/Rev/derek-lieu.com style guides): ~17 characters/second
// is a comfortable reading pace (20-30cps is the cited comfortable range,
// but this stays on the conservative end since these are short live
// fragments, not full sentences), 7s is a ceiling so a short cue doesn't
// linger long after its dialogue plausibly ended, and roll-up captioning is
// conventionally capped at 2-4 simultaneously visible lines with the oldest
// evicted as a new one arrives.
//
// LIVE_CAPTION_MIN_DISPLAY_SECONDS is deliberately at the top of the
// commonly-cited 1.5-2s minimum-hold range rather than some lower FCC floor:
// the backend's ccextractor dedup (see captions_live.py) strips each roll-up
// cue down to just its genuinely new line(s), which for CEA-608's frequent
// small flush increments is routinely only a word or two - so this floor is
// what actually keeps a short fragment readable rather than flashing by, and
// it doubles as the minimum spacing between consecutive stretched cues
// (nextStretchSlotAbsolute), which keeps hand-offs from happening faster
// than the also-cited "avoid <1s gaps" guidance.
const LIVE_CAPTION_CPS = 17;
const LIVE_CAPTION_MIN_DISPLAY_SECONDS = 1.5;
const LIVE_CAPTION_MAX_DISPLAY_SECONDS = 7;
const LIVE_CAPTION_MAX_VISIBLE_LINES = 2;
// Caps how far a burst of stale cues delivered in one poll can be staggered
// into the future (see appendCaptionCues). A roll-up decoder that flushes a
// cue per line increment (rather than once per completed line) can hand back
// a huge backlog - e.g. every cue produced since capture start, on the very
// first poll after enabling captions mid-show. Staggering all of them
// LIVE_CAPTION_MIN_DISPLAY_SECONDS apart would queue the caption display
// minutes into the future, reading as "captions stopped." Past this cap,
// further backlog cues are left unstretched (inert history, visible only on
// rewind) instead of extending the queue - real time catches back up to
// nextStretchSlotAbsolute within this many seconds either way.
const LIVE_CUE_MAX_CATCHUP_SECONDS = 20;

// A caption's display duration scales with how much there is to read,
// clamped to the min/max hold above.
function computeLiveCueDisplaySeconds(text: string): number {
	const charCount = text.replace(/\n/g, ' ').length;
	const readSeconds = charCount / LIVE_CAPTION_CPS;
	return Math.min(LIVE_CAPTION_MAX_DISPLAY_SECONDS, Math.max(LIVE_CAPTION_MIN_DISPLAY_SECONDS, readSeconds));
}

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
	// Every currently-visible stretched cue, oldest first, bounded to
	// LIVE_CAPTION_MAX_VISIBLE_LINES - see appendCaptionCues. Rebuilt in
	// replay order whenever the whole history is re-rendered (refreshCaptionCues),
	// so it stays consistent with whichever VTTCue objects are actually on the
	// live TextTrack right now.
	let openLiveCues: { cue: CaptionCue; vttCue: VTTCue }[] = [];

	// Drops entries whose display window has already ended by `beforeAbsolute`.
	function pruneOpenLiveCues(beforeAbsolute: number) {
		while (openLiveCues.length > 0 && (openLiveCues[0].cue.displayEnd ?? -Infinity) <= beforeAbsolute) {
			openLiveCues.shift();
		}
	}

	function ensureCaptionTrack() {
		const videoElement = options.getVideoElement();
		if (capTextTrack || !videoElement) return;
		capTextTrack = videoElement.addTextTrack('subtitles', 'Captions', 'en');
		// Always hidden: the player's own .caption-overlay (positioned above
		// the scrub bar) is the only caption UI - this track exists just to
		// hold cue timing, and letting it go 'showing' would double-render
		// every line via the browser's native subtitle rendering too.
		capTextTrack.mode = 'hidden';
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
		if (allowStretch && isInProgress && videoElement) {
			// Anchor this call's stagger window to *now*, not to wherever a
			// previous, separate poll last left the cursor. Roll-up cues
			// routinely arrive faster than LIVE_CUE_MIN_DISPLAY_SECONDS apart
			// (observed as low as ~0.4s between consecutive cues) - without
			// this reset, nextStretchSlotAbsolute drifts further ahead of
			// real time on every single cue and never catches back up, so
			// every cue after the first queues up behind a permanently
			// growing backlog instead of displaying. Staggering is only
			// needed to keep multiple cues *within this same batch* from
			// overlapping, so it's safe to forget an older reservation
			// whenever a new poll comes in.
			nextStretchSlotAbsolute = baseOffsetSeconds + videoElement.currentTime;
		}
		for (const cue of cues) {
			if (allowStretch && isInProgress && videoElement && cue.displayEnd === undefined) {
				const naturalEnd = cue.end - baseOffsetSeconds;
				// See LIVE_CAPTION_MIN_DISPLAY_SECONDS: while live, a cue that's
				// already past its natural end by the time it arrives gets held
				// on screen for a bit instead of being dropped as stale.
				if (naturalEnd <= videoElement.currentTime) {
					const nowAbsolute = baseOffsetSeconds + videoElement.currentTime;
					pruneOpenLiveCues(nowAbsolute);
					// If LIVE_CAPTION_MAX_VISIBLE_LINES cues are already open, the
					// new cue can't start before the oldest has had at least its
					// guaranteed minimum hold - otherwise it'd get evicted (below)
					// before a reader had a real chance to see it.
					const capFloor =
						openLiveCues.length >= LIVE_CAPTION_MAX_VISIBLE_LINES
							? (openLiveCues[0].cue.displayStart ?? 0) + LIVE_CAPTION_MIN_DISPLAY_SECONDS
							: 0;
					const slotStart = Math.max(cue.start, nextStretchSlotAbsolute, nowAbsolute, capFloor);
					// See LIVE_CUE_MAX_CATCHUP_SECONDS: past the cap, stop handing
					// out further slots - leave the rest of a large backlog burst
					// as unstretched history instead of queuing it arbitrarily far
					// into the future.
					if (slotStart - nowAbsolute <= LIVE_CUE_MAX_CATCHUP_SECONDS) {
						cue.displayStart = slotStart;
						cue.displayEnd = slotStart + computeLiveCueDisplaySeconds(cue.text);
						nextStretchSlotAbsolute = cue.displayEnd;
					}
				}
			}
			const start = (cue.displayStart ?? cue.start) - baseOffsetSeconds;
			const end = (cue.displayEnd ?? cue.end) - baseOffsetSeconds;
			if (end <= 0) continue;
			try {
				const vttCue = new VTTCue(Math.max(0, start), end, cue.text);
				capTextTrack.addCue(vttCue);
				// Bounded roll-up bookkeeping: only cues that were ever stretched
				// (displayStart set, above or on a previous call) participate -
				// natural, never-stale cues aren't subject to the 2-line cap.
				if (cue.displayStart !== undefined) {
					pruneOpenLiveCues(cue.displayStart);
					if (openLiveCues.length >= LIVE_CAPTION_MAX_VISIBLE_LINES) {
						const evicted = openLiveCues.shift();
						if (evicted) {
							// Truncate both the shared cue data and the hidden
							// TextTrack's cue (used by AirPlay/casting) so the two
							// stay consistent with what's on screen.
							evicted.cue.displayEnd = cue.displayStart;
							evicted.vttCue.endTime = cue.displayStart - baseOffsetSeconds;
						}
					}
					openLiveCues.push({ cue, vttCue });
				}
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
		// Rebuilding from scratch: forget the old open-cue bookkeeping instead
		// of carrying over entries that point at VTTCue objects just removed
		// above - appendCaptionCues repopulates it fresh, in order, as it
		// replays history against the (possibly still-open) same cue objects.
		openLiveCues = [];
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
			// Keep the previously-parsed cue objects (and whatever displayStart/
			// displayEnd stretching already decided for them) rather than the
			// freshly re-parsed ones - a full re-parse-and-replace here would
			// silently discard that decision on every poll and could make an
			// already-stretched, still-visible cue revert to its raw (already
			// expired) natural timing and disappear early.
			options.setCaptionCues([...existingCues, ...newCues]);
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

	// A stale slot from before a seek is on the old absolute clock and
	// could push a freshly-stretched cue arbitrarily far into the future
	// relative to the new origin.
	function resetStretchCursor() {
		nextStretchSlotAbsolute = 0;
		openLiveCues = [];
	}

	function teardown() {
		capTextTrack = null;
		nextStretchSlotAbsolute = 0;
		openLiveCues = [];
	}

	// CC-14: switching between caption tracks (e.g. CEA-608 channel 1/2)
	// points getCaptionsUrl() at a different sidecar entirely, so the old
	// track's cue history and stretch cursor are meaningless on the new one -
	// clear both, plus whatever's already rendered on the native TextTrack,
	// before the caller re-fetches via loadCaptions().
	function switchCaptionTrack() {
		options.setCaptionCues([]);
		resetStretchCursor();
		if (capTextTrack) {
			while (capTextTrack.cues && capTextTrack.cues.length > 0) {
				capTextTrack.removeCue(capTextTrack.cues[0]);
			}
		}
	}

	return {
		ensureCaptionTrack,
		refreshCaptionCues,
		loadCaptions,
		pollLiveCaptions,
		maybeResyncBaseOffset,
		resetStretchCursor,
		switchCaptionTrack,
		teardown,
	};
}
