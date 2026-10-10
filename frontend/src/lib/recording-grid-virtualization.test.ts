import { describe, expect, it } from 'vitest';
import {
	computeColumnsPerRow,
	computeColumnWidth,
	computeRowHeight,
	computeVisibleRowRange,
} from './recording-grid-virtualization';

describe('recording-grid-virtualization', () => {
	describe('computeColumnsPerRow', () => {
		it('fits one column into a narrow container', () => {
			expect(computeColumnsPerRow(200)).toBe(1);
		});

		it('fits multiple columns matching the auto-fill minmax(11rem, 1fr) CSS', () => {
			// 4 columns of 176px + 3 gaps of 16px = 752px
			expect(computeColumnsPerRow(752)).toBe(4);
			// one pixel short of fitting a 4th column
			expect(computeColumnsPerRow(751)).toBe(3);
		});

		it('never returns less than 1 for a zero or negative width', () => {
			expect(computeColumnsPerRow(0)).toBe(1);
			expect(computeColumnsPerRow(-50)).toBe(1);
		});
	});

	describe('computeColumnWidth', () => {
		it('divides the container evenly across columns, accounting for gaps', () => {
			expect(computeColumnWidth(752, 4)).toBeCloseTo(176, 5);
		});

		it('falls back to the full width when columns is not positive', () => {
			expect(computeColumnWidth(400, 0)).toBe(400);
		});
	});

	describe('computeRowHeight', () => {
		it('scales with column width via the poster aspect ratio plus fixed text block', () => {
			const narrow = computeRowHeight(176);
			const wide = computeRowHeight(352);
			expect(wide).toBeGreaterThan(narrow);
			// poster height alone should dominate the difference (176 * 1.5 = 264 more)
			expect(wide - narrow).toBeCloseTo(264, 5);
		});
	});

	describe('computeVisibleRowRange', () => {
		it('returns the full range (minus overscan clamp) when everything fits in the viewport', () => {
			const range = computeVisibleRowRange({
				scrollTopWithinGridPx: 0,
				viewportHeightPx: 1000,
				rowHeightPx: 300,
				totalRows: 3,
			});
			expect(range).toEqual({ startRow: 0, endRow: 3 });
		});

		it('windows to only the rows near the scroll position, with overscan', () => {
			const range = computeVisibleRowRange({
				scrollTopWithinGridPx: 3000,
				viewportHeightPx: 500,
				rowHeightPx: 300,
				totalRows: 100,
				overscanRows: 2,
			});
			// scrollTop/rowHeight = 10, minus overscan 2 = 8
			expect(range.startRow).toBe(8);
			// (3000+500)/300 = 11.67 -> ceil 12, plus overscan 2 = 14
			expect(range.endRow).toBe(14);
		});

		it('clamps the end row to totalRows', () => {
			const range = computeVisibleRowRange({
				scrollTopWithinGridPx: 0,
				viewportHeightPx: 500,
				rowHeightPx: 300,
				totalRows: 2,
				overscanRows: 5,
			});
			expect(range.endRow).toBe(2);
		});

		it('returns an empty range for zero rows or zero row height', () => {
			expect(
				computeVisibleRowRange({ scrollTopWithinGridPx: 0, viewportHeightPx: 500, rowHeightPx: 300, totalRows: 0 }),
			).toEqual({ startRow: 0, endRow: 0 });
			expect(
				computeVisibleRowRange({ scrollTopWithinGridPx: 0, viewportHeightPx: 500, rowHeightPx: 0, totalRows: 10 }),
			).toEqual({ startRow: 0, endRow: 0 });
		});
	});
});
