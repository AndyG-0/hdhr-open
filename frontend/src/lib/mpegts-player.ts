import type Mpegts from 'mpegts.js';

interface MpegtsPlayerOptions {
	getDestroyed: () => boolean;
	setErrorMessage: (message: string | null) => void;
	setErrorDetail: (detail: string | null) => void;
	genericHint: () => string;
}

// Owns the mpegts.js player instance's lifecycle - creation (via a dynamic
// import, since the library touches `window` at import time and would
// otherwise crash SvelteKit's server-side render), teardown, and the
// error-detail re-fetch workaround below. attachPlayer() in the component
// remains the DOM-binding seam that calls into this.
export function createMpegtsPlayer(options: MpegtsPlayerOptions) {
	let player: ReturnType<typeof Mpegts.createPlayer> | undefined;
	// Guards against a create-player race: createPlayerAt() does an async
	// `import('mpegts.js')` before it can construct/assign a player, so two
	// calls in quick succession (e.g. a fast channel switch) can have their
	// imports resolve out of order. Each call captures the generation at the
	// moment it starts; when its import resolves, it only proceeds if it's
	// still the most recent call - otherwise it destroys the player it just
	// built (rather than assigning it) and bails, leaving the real latest
	// call's player in place.
	let generation = 0;

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

	function destroyPlayerInstance(instance: ReturnType<typeof Mpegts.createPlayer>) {
		instance.pause();
		instance.unload();
		instance.detachMediaElement();
		instance.destroy();
	}

	function teardownPlayer() {
		// Invalidate any in-flight createPlayerAt() call too, so its import
		// doesn't resolve later and silently resurrect a player after an
		// explicit teardown.
		generation++;
		if (player) destroyPlayerInstance(player);
		player = undefined;
	}

	// Live download-speed + decode telemetry from the MSE loader - `speed`
	// (KB/s) feeds the throughput-based half of quality auto-adjustment (see
	// sampleThroughput() in HDHomeRunPlayer.svelte), while decodedFrames/
	// droppedFrames feed the "stats for nerds" panel. We always construct
	// with `type: 'mse'`, so the runtime shape is always
	// MSEPlayerStatisticsInfo even though `player`'s declared type permits
	// NativePlayer's narrower one too; `speed` is only populated once a
	// segment has actually loaded.
	function getStatisticsInfo(): Partial<Mpegts.MSEPlayerStatisticsInfo> | null {
		return (player?.statisticsInfo as Partial<Mpegts.MSEPlayerStatisticsInfo> | undefined) ?? null;
	}

	// Ground-truth info about the stream actually being decoded right now -
	// used for the "stats for nerds" panel in HDHomeRunPlayer.svelte, as
	// opposed to the server's probe of the *source* recording/tuner file
	// (which never changes when a quality tier switch changes the real
	// encode). width/height/fps/videoCodec come from real demuxed SPS/codec
	// parsing in mpegts.js, not from container metadata, so they're reliable
	// even for MPEG-TS (unlike videoDataRate/audioDataRate, which mpegts.js
	// only ever populates from FLV metadata tags that MPEG-TS never carries).
	function getMediaInfo(): Partial<Mpegts.MSEPlayerMediaInfo> | null {
		return (player?.mediaInfo as Partial<Mpegts.MSEPlayerMediaInfo> | undefined) ?? null;
	}

	function createPlayerAt(node: HTMLVideoElement, url: string) {
		options.setErrorMessage(null);
		options.setErrorDetail(null);
		// Bump synchronously (before the async import below starts) so each
		// call gets a distinct generation the instant it's invoked, not once
		// the import resolves - that's what lets a later call's generation
		// bump happen-before an earlier call's post-import check.
		const myGeneration = ++generation;
		// mpegts.js's UMD bundle references `window` at import time, so a
		// static import would crash SvelteKit's server-side render of this
		// page (Node has no `window`). Deferring to a dynamic import here
		// means it only ever loads client-side, once this action runs.
		import('mpegts.js').then(({ default: mpegts }) => {
			if (options.getDestroyed()) return;
			// A newer createPlayerAt()/teardownPlayer() call has started since
			// this one began (e.g. a fast channel switch firing two calls in
			// quick succession) - proceeding would race whatever that newer
			// call has done to `player`. Build the instance so we have
			// something to clean up (construction itself is cheap and
			// synchronous - it's attach/load/play that actually engage the
			// network and DOM), destroy it immediately, and bail instead of
			// assigning it over the latest call's player.
			const newPlayer = mpegts.createPlayer(
				{ type: 'mse', isLive: true, url, withCredentials: true },
				{
					// A small jitter cushion so a brief network hiccup drains the
					// stash instead of starving the decoder outright - this is the
					// client-side half of the stutter fix (the other half is the
					// server-side bitrate ceiling in transcoding.py). Large enough to
					// absorb a short stall, small enough not to add noticeable extra
					// live latency.
					enableStashBuffer: true,
					stashInitialSize: 768 * 1024,
					// liveBufferLatencyChasing auto-seeks forward whenever the playhead
					// falls behind the live edge — which is exactly what a manual
					// buffer-rewind (see rewind()/fastForward() in the component) does,
					// so leaving it on snaps the video straight back to live the
					// instant you scrub backward. Off, so a manual seek stays where
					// you put it.
					liveBufferLatencyChasing: false,
				},
			);
			if (myGeneration !== generation) {
				destroyPlayerInstance(newPlayer);
				return;
			}
			player = newPlayer;
			player.on(mpegts.Events.ERROR, (errorType: string) => {
				options.setErrorMessage(options.genericHint());
				if (errorType !== mpegts.ErrorTypes.NETWORK_ERROR) return;
				fetchServerDetail(url).then((detail) => {
					if (!options.getDestroyed()) options.setErrorDetail(detail);
				});
			});
			player.attachMediaElement(node);
			player.load();
			player.play();
		});
	}

	return { createPlayerAt, teardownPlayer, fetchServerDetail, getStatisticsInfo, getMediaInfo };
}
