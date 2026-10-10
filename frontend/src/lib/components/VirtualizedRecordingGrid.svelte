<script lang="ts">
	import type { HDHomeRunRecording } from '$lib/api';
	import RecordingCard from '$lib/components/RecordingCard.svelte';
	import {
		computeColumnsPerRow,
		computeColumnWidth,
		computeRowHeight,
		computeVisibleRowRange,
		VIRTUALIZATION_THRESHOLD,
	} from '$lib/recording-grid-virtualization';

	interface Props {
		items: HDHomeRunRecording[];
		failedImages: Record<string, boolean>;
		deletingRecordingId: string | null;
		onImageError: (recording: HDHomeRunRecording) => void;
		onPlay: (recording: HDHomeRunRecording) => void;
		onPopout: (recording: HDHomeRunRecording) => void;
		onDelete: (recording: HDHomeRunRecording) => void;
	}

	let { items, failedImages, deletingRecordingId, onImageError, onPlay, onPopout, onDelete }: Props = $props();

	let gridEl: HTMLDivElement | null = $state(null);
	let containerWidthPx = $state(0);
	let viewportHeightPx = $state(0);
	let scrollTopWithinGridPx = $state(0);

	const shouldVirtualize = $derived(items.length > VIRTUALIZATION_THRESHOLD);
	const columns = $derived(computeColumnsPerRow(containerWidthPx));
	const columnWidthPx = $derived(computeColumnWidth(containerWidthPx, columns));
	const rowHeightPx = $derived(computeRowHeight(columnWidthPx));
	const totalRows = $derived(Math.ceil(items.length / columns));

	const visibleRange = $derived(
		shouldVirtualize
			? computeVisibleRowRange({ scrollTopWithinGridPx, viewportHeightPx, rowHeightPx, totalRows })
			: { startRow: 0, endRow: totalRows },
	);

	const windowedItems = $derived(
		shouldVirtualize ? items.slice(visibleRange.startRow * columns, visibleRange.endRow * columns) : items,
	);
	const topSpacerPx = $derived(shouldVirtualize ? visibleRange.startRow * rowHeightPx : 0);
	const bottomSpacerPx = $derived(shouldVirtualize ? (totalRows - visibleRange.endRow) * rowHeightPx : 0);

	// Measured from the grid's own position in the viewport (rather than tracking
	// document scroll position separately) so it stays correct even when content
	// above the grid changes height for reasons that aren't a scroll/resize event.
	function updateScrollMetrics() {
		if (!gridEl) return;
		scrollTopWithinGridPx = Math.max(0, -gridEl.getBoundingClientRect().top);
		viewportHeightPx = window.innerHeight;
	}

	let scrollRafId: number | null = null;

	function onWindowScroll() {
		if (scrollRafId !== null) return;
		scrollRafId = requestAnimationFrame(() => {
			updateScrollMetrics();
			scrollRafId = null;
		});
	}

	$effect(() => {
		if (!shouldVirtualize) return;
		updateScrollMetrics();
		window.addEventListener('scroll', onWindowScroll, { passive: true });
		window.addEventListener('resize', onWindowScroll);
		return () => {
			window.removeEventListener('scroll', onWindowScroll);
			window.removeEventListener('resize', onWindowScroll);
			if (scrollRafId !== null) cancelAnimationFrame(scrollRafId);
			scrollRafId = null;
		};
	});

	$effect(() => {
		if (!gridEl) return;
		const el = gridEl;
		containerWidthPx = el.clientWidth;
		const observer = new ResizeObserver(() => {
			containerWidthPx = el.clientWidth;
		});
		observer.observe(el);
		return () => observer.disconnect();
	});
</script>

<div class="recordings" bind:this={gridEl}>
	{#if shouldVirtualize}
		<div class="grid-spacer" style={`height: ${topSpacerPx}px;`}></div>
	{/if}
	{#each windowedItems as recording, i (recording.recording_id ?? `${visibleRange.startRow * columns + i}`)}
		<RecordingCard
			{recording}
			variant="completed"
			failed={failedImages[recording.recording_id ?? ''] ?? false}
			onImageError={() => onImageError(recording)}
			onPlay={() => onPlay(recording)}
			onPopout={() => onPopout(recording)}
			onDelete={() => onDelete(recording)}
			deleting={deletingRecordingId === recording.recording_id}
		/>
	{/each}
	{#if shouldVirtualize}
		<div class="grid-spacer" style={`height: ${bottomSpacerPx}px;`}></div>
	{/if}
</div>

<style>
	.recordings {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
		gap: 1rem;
		margin: 0.5rem 0 1.5rem;
	}

	.grid-spacer {
		grid-column: 1 / -1;
	}
</style>
