import { api } from '$lib/api';

export interface AirPlayControllerOptions {
	getVideoElement: () => (HTMLVideoElement & { webkitShowPlaybackTargetPicker?: () => void }) | null;
	getDestroyed: () => boolean;
	getSeekable: () => boolean;
	getBaseOffsetSeconds: () => number;
	setBaseOffsetSeconds: (value: number) => void;
	getVideoCurrentTime: () => number;
	setVideoCurrentTime: (value: number) => void;
	getCurrentAudioIndex: () => number | null;
	getSrc: () => string;
	buildStreamUrl: (resumeAt: number, audioIndex?: number | null) => string;
	buildCastContentUrl: () => Promise<{ url: string; sessionId: string }>;
	onAvailabilityChange?: (available: boolean) => void;
	teardownMpegtsPlayer: () => void;
	createMpegtsPlayerAt: (video: HTMLVideoElement, url: string) => void;
	safePlay: () => void;
	stopHlsSession?: (sessionId: string) => void;
	refreshCaptions?: () => void;
}

export interface AirPlayController {
	isAirPlaySupported: () => boolean;
	isAirPlayAvailable: () => boolean;
	getAirPlaySessionId: () => string | null;
	showAirPlayPicker: () => void;
	startAirPlayPlayback: () => Promise<void>;
	stopAirPlayPlayback: () => void;
	attachVideoElement: (video: (HTMLVideoElement & { webkitShowPlaybackTargetPicker?: () => void }) | null) => () => void;
	destroy: () => void;
}

export function isAirPlaySupported(): boolean {
	return (
		typeof window !== 'undefined' &&
		('WebKitPlaybackTargetAvailabilityEvent' in window ||
			'WebKitPlaybackTargetAvailabilityEvent' in (globalThis as unknown as Record<string, unknown>))
	);
}

export function createAirPlayController(options: AirPlayControllerOptions): AirPlayController {
	let airplayAvailable = false;
	let airplaySessionId: string | null = null;
	let airplayResumeFrom = 0;

	const stopHls = options.stopHlsSession ?? api.stopHlsSession;

	function showAirPlayPicker() {
		const video = options.getVideoElement();
		video?.webkitShowPlaybackTargetPicker?.();
	}

	async function startAirPlayPlayback(): Promise<void> {
		const video = options.getVideoElement();
		if (!video || airplaySessionId) return;

		try {
			airplayResumeFrom = options.getSeekable()
				? options.getBaseOffsetSeconds() + options.getVideoCurrentTime()
				: 0;

			const { url, sessionId } = await options.buildCastContentUrl();
			const currentVideo = options.getVideoElement();
			if (!currentVideo || options.getDestroyed() || !airplayAvailable) {
				stopHls(sessionId);
				return;
			}

			airplaySessionId = sessionId;
			options.teardownMpegtsPlayer();
			currentVideo.removeAttribute('crossorigin');
			currentVideo.src = url;
			currentVideo.load();
			options.safePlay();
		} catch {
			// Best-effort: failures leave MSE player intact
		}
	}

	function stopAirPlayPlayback(): void {
		if (!airplaySessionId) return;
		stopHls(airplaySessionId);
		airplaySessionId = null;

		const video = options.getVideoElement();
		if (!video || options.getDestroyed()) return;

		video.setAttribute('crossorigin', 'use-credentials');
		video.removeAttribute('src');
		video.load();

		if (options.getSeekable()) {
			const resumeAt = airplayResumeFrom + video.currentTime;
			options.setBaseOffsetSeconds(resumeAt);
			options.setVideoCurrentTime(0);
			options.refreshCaptions?.();
			options.createMpegtsPlayerAt(
				video,
				options.buildStreamUrl(resumeAt, options.getCurrentAudioIndex()),
			);
		} else {
			options.createMpegtsPlayerAt(video, options.getSrc());
		}
	}

	function attachVideoElement(
		video: (HTMLVideoElement & { webkitShowPlaybackTargetPicker?: () => void }) | null,
	): () => void {
		if (!video || !isAirPlaySupported()) return () => {};

		const handleAvailabilityChange = (event: Event) => {
			airplayAvailable = (event as unknown as { availability: string }).availability === 'available';
			options.onAvailabilityChange?.(airplayAvailable);
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
	}

	function destroy(): void {
		if (airplaySessionId) {
			stopHls(airplaySessionId);
			airplaySessionId = null;
		}
	}

	return {
		isAirPlaySupported,
		isAirPlayAvailable: () => airplayAvailable,
		getAirPlaySessionId: () => airplaySessionId,
		showAirPlayPicker,
		startAirPlayPlayback,
		stopAirPlayPlayback,
		attachVideoElement,
		destroy,
	};
}
