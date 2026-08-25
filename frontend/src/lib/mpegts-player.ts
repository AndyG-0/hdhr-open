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
		options.setErrorMessage(null);
		options.setErrorDetail(null);
		// mpegts.js's UMD bundle references `window` at import time, so a
		// static import would crash SvelteKit's server-side render of this
		// page (Node has no `window`). Deferring to a dynamic import here
		// means it only ever loads client-side, once this action runs.
		import('mpegts.js').then(({ default: mpegts }) => {
			if (options.getDestroyed()) return;
			player = mpegts.createPlayer(
				{ type: 'mse', isLive: true, url, withCredentials: true },
				// liveBufferLatencyChasing auto-seeks forward whenever the playhead
				// falls behind the live edge — which is exactly what a manual
				// buffer-rewind (see rewind()/fastForward() in the component) does,
				// so leaving it on snaps the video straight back to live the
				// instant you scrub backward. Off, so a manual seek stays where
				// you put it.
				{ enableStashBuffer: false, liveBufferLatencyChasing: false },
			);
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

	return { createPlayerAt, teardownPlayer, fetchServerDetail };
}
