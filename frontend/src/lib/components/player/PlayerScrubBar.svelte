<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { CommercialSegment } from '$lib/api';
	import type { ThumbnailCue } from '$lib/vtt-parser';

	interface Props {
		displayedPosition: number;
		duration: number | null;
		isInProgress?: boolean;
		seekable?: boolean;
		thumbnailsAvailable?: boolean;
		thumbSpriteUrl?: string;
		thumbnailCues?: ThumbnailCue[];
		commercialSegments?: CommercialSegment[];
		onSeek: (targetSeconds: number) => void;
	}

	let {
		displayedPosition,
		duration,
		isInProgress = false,
		seekable = true,
		thumbnailsAvailable = false,
		thumbSpriteUrl = '',
		thumbnailCues = [],
		commercialSegments = [],
		onSeek,
	}: Props = $props();

	let scrubBarEl = $state<HTMLDivElement | null>(null);
	let hoverPreview = $state<{ x: number; cue: ThumbnailCue; time: number } | null>(null);
	let showRemaining = $state(true);
	let isDragging = $state(false);
	// Tracks the pointer during a drag so the thumb/time move smoothly even
	// though the actual onSeek() call is throttled (see scheduleThrottledSeek) -
	// null outside of a drag, when displayedPosition is the source of truth.
	let dragPreviewSeconds = $state<number | null>(null);

	// Every onSeek() tears down and recreates the whole backend transcode
	// pipeline (a fresh ffmpeg process). Calling it on every pointermove during
	// a drag can spawn a dozen overlapping ffmpeg processes within a second,
	// which exhausts hardware encoder sessions (e.g. macOS VideoToolbox allows
	// only a few concurrent sessions) and makes most of them fail outright -
	// surfacing to the client as a 502. Throttling keeps at most one real seek
	// in flight per window, while still always landing on the final released
	// position.
	const SEEK_THROTTLE_MS = 400;
	let pendingSeekTimer: ReturnType<typeof setTimeout> | null = null;
	let lastSeekAt = 0;
	let latestDragTarget: number | null = null;

	const displayPosition = $derived(dragPreviewSeconds ?? displayedPosition);

	const progressPercent = $derived(
		duration && duration > 0 ? Math.min(100, Math.max(0, (displayPosition / duration) * 100)) : 0,
	);

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

	const rightTimestampText = $derived.by<string>(() => {
		if (isInProgress) {
			return $_('hdhomerun.detail.recording_in_progress', { default: 'Recording in progress' });
		}
		if (duration === null || duration <= 0) return '0:00';
		if (showRemaining) {
			const remaining = Math.max(0, duration - displayPosition);
			return `-${formatTime(remaining)}`;
		}
		return formatTime(duration);
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

	function targetSecondsAt(clientX: number): number | null {
		if (!seekable || duration === null || !scrubBarEl) return null;
		const rect = scrubBarEl.getBoundingClientRect();
		const fraction = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
		return fraction * duration;
	}

	function clearPendingSeek() {
		if (pendingSeekTimer !== null) {
			clearTimeout(pendingSeekTimer);
			pendingSeekTimer = null;
		}
	}

	// Fires onSeek() right away - for a discrete click/tap and for the final
	// position on drag release, both of which must take effect immediately.
	function commitSeek(targetSeconds: number) {
		clearPendingSeek();
		lastSeekAt = Date.now();
		onSeek(targetSeconds);
	}

	// Fires onSeek() at most once per SEEK_THROTTLE_MS while dragging. Repeated
	// calls just update latestDragTarget/dragPreviewSeconds cheaply; only one
	// timer is ever pending, and it always reads the latest target rather than
	// whichever position was current when it was scheduled.
	function scheduleThrottledSeek(targetSeconds: number) {
		latestDragTarget = targetSeconds;
		const elapsed = Date.now() - lastSeekAt;
		if (elapsed >= SEEK_THROTTLE_MS) {
			commitSeek(targetSeconds);
			return;
		}
		if (pendingSeekTimer !== null) return;
		pendingSeekTimer = setTimeout(() => {
			pendingSeekTimer = null;
			if (latestDragTarget !== null) commitSeek(latestDragTarget);
		}, SEEK_THROTTLE_MS - elapsed);
	}

	function updateHover(clientX: number) {
		if (!scrubBarEl) return;
		const rect = scrubBarEl.getBoundingClientRect();
		const fraction = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
		const time = duration !== null ? fraction * duration : 0;

		if (seekable && duration !== null && thumbnailsAvailable) {
			const cue = findCueAt(time);
			if (cue) {
				hoverPreview = { x: clientX - rect.left, cue, time };
			} else {
				hoverPreview = null;
			}
		} else if (seekable && duration !== null) {
			hoverPreview = {
				x: clientX - rect.left,
				cue: { startSeconds: time, endSeconds: time, x: 0, y: 0, w: 0, h: 0 },
				time,
			};
		}
	}

	function handleClick(e: MouseEvent) {
		const target = targetSecondsAt(e.clientX);
		if (target !== null) commitSeek(target);
	}

	function handleMouseMove(e: MouseEvent) {
		updateHover(e.clientX);
		if (isDragging) {
			const target = targetSecondsAt(e.clientX);
			if (target !== null) {
				dragPreviewSeconds = target;
				scheduleThrottledSeek(target);
			}
		}
	}

	function handlePointerDown(e: PointerEvent) {
		if (!seekable || duration === null || !scrubBarEl) return;
		isDragging = true;
		try {
			scrubBarEl.setPointerCapture(e.pointerId);
		} catch {
			// ignore
		}
		const target = targetSecondsAt(e.clientX);
		if (target !== null) {
			dragPreviewSeconds = target;
			commitSeek(target);
		}
	}

	function handlePointerMove(e: PointerEvent) {
		updateHover(e.clientX);
		if (isDragging) {
			const target = targetSecondsAt(e.clientX);
			if (target !== null) {
				dragPreviewSeconds = target;
				scheduleThrottledSeek(target);
			}
		}
	}

	function handlePointerUp(e: PointerEvent) {
		if (!isDragging) return;
		isDragging = false;
		if (scrubBarEl) {
			try {
				scrubBarEl.releasePointerCapture(e.pointerId);
			} catch {
				// ignore
			}
		}
		// Always land exactly where the drag was released, even if a throttled
		// seek for an earlier point in the drag is still pending.
		if (dragPreviewSeconds !== null) commitSeek(dragPreviewSeconds);
		dragPreviewSeconds = null;
	}

	function handleMouseLeave() {
		if (!isDragging) {
			hoverPreview = null;
		}
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (!seekable || duration === null) return;
		if (e.key === 'ArrowLeft') {
			e.preventDefault();
			commitSeek(Math.max(0, displayedPosition - 10));
		} else if (e.key === 'ArrowRight') {
			e.preventDefault();
			commitSeek(Math.min(duration, displayedPosition + 10));
		}
	}

	function toggleRemaining() {
		showRemaining = !showRemaining;
	}
</script>

<div class="scrub-container">
	<span class="scrub-time left">{formatTime(displayPosition)}</span>

	<div
		class="scrub-bar"
		class:disabled={!seekable || duration === null}
		bind:this={scrubBarEl}
		onclick={handleClick}
		onmousemove={handleMouseMove}
		onmouseleave={handleMouseLeave}
		onpointerdown={handlePointerDown}
		onpointermove={handlePointerMove}
		onpointerup={handlePointerUp}
		onpointercancel={handlePointerUp}
		onkeydown={handleKeyDown}
		role="slider"
		aria-label={$_('player.playback_info', { default: 'Playback Seek' })}
		aria-valuemin="0"
		aria-valuemax={duration ?? 0}
		aria-valuenow={displayPosition}
		tabindex="0"
	>
		<div class="scrub-track">
			{#if duration && duration > 0}
				{#each commercialSegments as segment (segment.start_seconds)}
					<div
						class="commercial-band"
						style:left="{(Math.max(0, segment.start_seconds) / duration) * 100}%"
						style:width="{((Math.min(duration, segment.end_seconds) - Math.max(0, segment.start_seconds)) / duration) * 100}%"
					></div>
				{/each}
			{/if}
			<div class="scrub-fill" style:width="{progressPercent}%"></div>
			{#if seekable && duration !== null}
				<div class="scrub-thumb" style:left="{progressPercent}%"></div>
			{/if}
		</div>

		{#if hoverPreview}
			<div
				class="thumb-preview"
				style:left="{hoverPreview.x}px"
				style:width={hoverPreview.cue.w > 0 ? `${hoverPreview.cue.w}px` : 'auto'}
				style:height={hoverPreview.cue.h > 0 ? `${hoverPreview.cue.h}px` : 'auto'}
				style:background-image={hoverPreview.cue.w > 0 ? `url(${thumbSpriteUrl})` : 'none'}
				style:background-position="-{hoverPreview.cue.x}px -{hoverPreview.cue.y}px"
			>
				<span class="thumb-time">{formatTime(hoverPreview.cue.startSeconds)}</span>
			</div>
		{/if}
	</div>

	<button
		type="button"
		class="scrub-time right btn-toggle"
		onclick={toggleRemaining}
		aria-label={$_('player.toggle_time_format', { default: 'Toggle time format' })}
		title={$_('player.toggle_time_format', { default: 'Toggle remaining / total time' })}
	>
		{rightTimestampText}
	</button>
</div>

<style>
	.scrub-container {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		width: 100%;
		padding: 0 0.5rem;
		user-select: none;
	}

	.scrub-time {
		color: rgba(255, 255, 255, 0.85);
		font-size: 0.82rem;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
		font-weight: 500;
		white-space: nowrap;
		min-width: 3rem;
	}

	.scrub-time.left {
		text-align: left;
	}

	.scrub-time.right {
		text-align: right;
	}

	.btn-toggle {
		background: none;
		border: none;
		cursor: pointer;
		padding: 0.2rem 0.35rem;
		border-radius: 0.25rem;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.btn-toggle:hover {
		background: rgba(255, 255, 255, 0.15);
		color: #ffffff;
	}

	.scrub-bar {
		position: relative;
		flex: 1;
		cursor: pointer;
		padding: 0.6rem 0;
		touch-action: none;
		outline: none;
	}

	.scrub-bar.disabled {
		cursor: default;
		opacity: 0.4;
		pointer-events: none;
	}

	.scrub-track {
		position: relative;
		height: 0.3rem;
		border-radius: 0.15rem;
		background: rgba(255, 255, 255, 0.25);
		transition: height 0.15s ease;
	}

	.scrub-bar:hover .scrub-track,
	.scrub-bar:focus-visible .scrub-track {
		height: 0.45rem;
	}

	.scrub-fill {
		position: absolute;
		top: 0;
		left: 0;
		height: 100%;
		background: #38bdf8;
		border-radius: 0.15rem;
	}

	.commercial-band {
		position: absolute;
		top: 0;
		height: 100%;
		background: rgba(251, 191, 36, 0.55);
		pointer-events: none;
	}

	.scrub-thumb {
		position: absolute;
		top: 50%;
		width: 0.85rem;
		height: 0.85rem;
		border-radius: 50%;
		background: #38bdf8;
		box-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
		transform: translate(-50%, -50%);
		transition: transform 0.1s ease, width 0.1s ease, height 0.1s ease;
	}

	.scrub-bar:hover .scrub-thumb,
	.scrub-bar:focus-visible .scrub-thumb {
		transform: translate(-50%, -50%) scale(1.25);
	}

	.thumb-preview {
		position: absolute;
		bottom: 100%;
		margin-bottom: 0.6rem;
		transform: translateX(-50%);
		border: 2px solid rgba(255, 255, 255, 0.9);
		border-radius: 0.35rem;
		background-repeat: no-repeat;
		box-shadow: 0 6px 16px rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: flex-end;
		justify-content: center;
		pointer-events: none;
		z-index: 130;
		background-color: rgba(15, 15, 15, 0.95);
	}

	.thumb-time {
		background: rgba(0, 0, 0, 0.85);
		color: #ffffff;
		font-size: 0.7rem;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
		font-weight: 600;
		padding: 0.1rem 0.35rem;
		border-radius: 0.2rem;
		margin: 0.25rem;
		white-space: nowrap;
	}
</style>
