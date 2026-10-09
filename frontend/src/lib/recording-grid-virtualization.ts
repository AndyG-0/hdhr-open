/** Pure math for virtualizing the recordings grid's DOM: how many columns
 * fit a given width (mirroring the `.recordings` grid's own
 * `repeat(auto-fill, minmax(11rem, 1fr))` CSS), and which row range is
 * visible for a given scroll position. Kept dependency-free (no DOM/
 * ResizeObserver) so it's unit-testable directly - jsdom's ResizeObserver
 * is a no-op, so any DOM-measuring logic can't be exercised this way.
 */

export const GRID_MIN_COLUMN_WIDTH_PX = 176; // 11rem at the default 16px root font size
export const GRID_GAP_PX = 16; // 1rem

// RecordingCard's poster is a fixed aspect-ratio (2/3) box, but the text
// block below it (title, clamped synopsis, badges, action buttons) is a
// handful of fixed-size pieces, not something worth measuring live - cards
// are uniform-height by design, so a constant estimate is good enough to
// window by (same justification as the guide grid's own rowHeightPx).
export const CARD_TEXT_BLOCK_HEIGHT_PX = 112;
export const CARD_VERTICAL_PADDING_PX = 22; // RecordingCard's 0.6rem + 0.75rem padding

/** Below this many items, skip virtualization entirely - the common small-
 * library case renders exactly as it did before this module existed. */
export const VIRTUALIZATION_THRESHOLD = 60;

export function computeColumnsPerRow(containerWidthPx: number): number {
	if (containerWidthPx <= 0) return 1;
	const columns = Math.floor((containerWidthPx + GRID_GAP_PX) / (GRID_MIN_COLUMN_WIDTH_PX + GRID_GAP_PX));
	return Math.max(1, columns);
}

export function computeColumnWidth(containerWidthPx: number, columns: number): number {
	if (columns <= 0 || containerWidthPx <= 0) return containerWidthPx;
	return (containerWidthPx - (columns - 1) * GRID_GAP_PX) / columns;
}

export function computeRowHeight(columnWidthPx: number): number {
	const posterHeightPx = columnWidthPx * 1.5; // aspect-ratio: 2 / 3 (width / height)
	return posterHeightPx + CARD_TEXT_BLOCK_HEIGHT_PX + CARD_VERTICAL_PADDING_PX + GRID_GAP_PX;
}

export interface VisibleRowRangeParams {
	scrollTopWithinGridPx: number;
	viewportHeightPx: number;
	rowHeightPx: number;
	totalRows: number;
	overscanRows?: number;
}

export interface VisibleRowRange {
	startRow: number;
	endRow: number;
}

export function computeVisibleRowRange({
	scrollTopWithinGridPx,
	viewportHeightPx,
	rowHeightPx,
	totalRows,
	overscanRows = 2,
}: VisibleRowRangeParams): VisibleRowRange {
	if (totalRows <= 0 || rowHeightPx <= 0) return { startRow: 0, endRow: 0 };
	const start = Math.max(0, Math.floor(scrollTopWithinGridPx / rowHeightPx) - overscanRows);
	const end = Math.min(totalRows, Math.ceil((scrollTopWithinGridPx + viewportHeightPx) / rowHeightPx) + overscanRows);
	return { startRow: start, endRow: Math.max(start, end) };
}
