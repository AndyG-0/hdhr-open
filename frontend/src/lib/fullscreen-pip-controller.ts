export interface FullscreenPipControllerOptions {
	getOverlayEl: () => HTMLDivElement | null;
	getVideoElement: () => HTMLVideoElement | null;
	getIsFullscreen: () => boolean;
	setIsFullscreen: (value: boolean) => void;
	setPipSupported: (value: boolean) => void;
	// Called after either toggle settles (success, no-op, or caught error) -
	// mirrors the resetAutoHideTimer() call every other control-chrome action
	// makes, so entering/exiting fullscreen or PiP counts as activity too.
	onToggled: () => void;
}

// Encapsulates fullscreen and Picture-in-Picture: the toggle actions
// (including their vendor-prefixed webkit fallbacks for Safari/iOS) and the
// document-level fullscreenchange listeners that keep isFullscreen/
// pipSupported in sync with reality (e.g. the browser's own Esc-to-exit-
// fullscreen, which fires fullscreenchange without ever calling
// toggleFullscreen()). All reactive state lives in the owning component and
// is threaded through via the getter/setter options above, same as the
// other player controllers.
export function createFullscreenPipController(options: FullscreenPipControllerOptions) {
	async function toggleFullscreen(): Promise<void> {
		if (typeof document === 'undefined') return;
		try {
			if (options.getIsFullscreen()) {
				if (document.exitFullscreen) {
					await document.exitFullscreen();
				} else if (
					(document as unknown as { webkitExitFullscreen?: () => Promise<void> }).webkitExitFullscreen
				) {
					await (document as unknown as { webkitExitFullscreen: () => Promise<void> }).webkitExitFullscreen();
				}
			} else {
				const target = options.getOverlayEl() ?? options.getVideoElement();
				if (target?.requestFullscreen) {
					await target.requestFullscreen();
				} else if (
					(target as unknown as { webkitRequestFullscreen?: () => Promise<void> })?.webkitRequestFullscreen
				) {
					await (
						target as unknown as { webkitRequestFullscreen: () => Promise<void> }
					).webkitRequestFullscreen();
				} else if (
					(options.getVideoElement() as unknown as { webkitEnterFullscreen?: () => void })
						?.webkitEnterFullscreen
				) {
					(
						options.getVideoElement() as unknown as { webkitEnterFullscreen: () => void }
					).webkitEnterFullscreen();
				}
			}
		} catch {
			// ignore
		}
		options.onToggled();
	}

	async function togglePip(): Promise<void> {
		const videoElement = options.getVideoElement();
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
		options.onToggled();
	}

	// Sets up the fullscreenchange listeners and initial pipSupported check -
	// call from a component $effect and return this function's own return
	// value as that effect's cleanup.
	function watch(): () => void {
		if (typeof document === 'undefined') return () => {};
		const updateFullscreen = () => {
			options.setIsFullscreen(
				Boolean(
					document.fullscreenElement ||
						(document as unknown as { webkitFullscreenElement?: Element }).webkitFullscreenElement,
				),
			);
		};
		document.addEventListener('fullscreenchange', updateFullscreen);
		document.addEventListener('webkitfullscreenchange', updateFullscreen);

		if ('pictureInPictureEnabled' in document) {
			options.setPipSupported(Boolean(document.pictureInPictureEnabled));
		}

		return () => {
			document.removeEventListener('fullscreenchange', updateFullscreen);
			document.removeEventListener('webkitfullscreenchange', updateFullscreen);
		};
	}

	return {
		toggleFullscreen,
		togglePip,
		watch,
	};
}
