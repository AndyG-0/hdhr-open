import { render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi, afterEach } from 'vitest';
import VirtualizedRecordingGrid from './VirtualizedRecordingGrid.svelte';
import type { HDHomeRunRecording } from '$lib/api';

function makeRecording(i: number): HDHomeRunRecording {
	return {
		recording_id: `rec-${i}`,
		title: `Recording ${i}`,
		channel_name: 'Test Channel',
		start: 1000 + i,
		record_end: 2000 + i,
	};
}

/** Stubs every element's clientWidth/getBoundingClientRect().top, and
 * window.innerHeight, so the grid's column/row math and scroll-position
 * read are deterministic - jsdom does no real layout. */
function stubLayout({
	clientWidthPx,
	gridTopPx,
	innerHeightPx,
}: {
	clientWidthPx: number;
	gridTopPx: number;
	innerHeightPx: number;
}) {
	Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
		configurable: true,
		value: clientWidthPx,
	});
	vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
		top: gridTopPx,
		bottom: gridTopPx,
		left: 0,
		right: 0,
		width: clientWidthPx,
		height: 0,
		x: 0,
		y: gridTopPx,
		toJSON() {
			return this;
		},
	} as DOMRect);
	Object.defineProperty(window, 'innerHeight', { configurable: true, value: innerHeightPx });
}

const noop = vi.fn();

describe('VirtualizedRecordingGrid.svelte', () => {
	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('renders every item with no spacers below the virtualization threshold', () => {
		const items = Array.from({ length: 10 }, (_, i) => makeRecording(i));
		const { container } = render(VirtualizedRecordingGrid, {
			props: {
				items,
				failedImages: {},
				deletingRecordingId: null,
				onImageError: noop,
				onPlay: noop,
				onPopout: noop,
				onDelete: noop,
			},
		});

		for (const recording of items) {
			expect(screen.getByText(recording.title)).toBeInTheDocument();
		}
		expect(container.querySelectorAll('.grid-spacer')).toHaveLength(0);
	});

	it('windows to only the rows near the scroll position above the virtualization threshold', () => {
		// 752px container -> 4 columns of 176px; grid flush with the top of the
		// viewport, so only the first few rows should actually be rendered.
		stubLayout({ clientWidthPx: 752, gridTopPx: 0, innerHeightPx: 1000 });

		const items = Array.from({ length: 100 }, (_, i) => makeRecording(i));
		const { container } = render(VirtualizedRecordingGrid, {
			props: {
				items,
				failedImages: {},
				deletingRecordingId: null,
				onImageError: noop,
				onPlay: noop,
				onPopout: noop,
				onDelete: noop,
			},
		});

		// Row height for a 176px column: 176*1.5 (poster) + 112 (text block) + 22
		// (card padding) + 16 (gap) = 414px. viewport 1000px / 414 ~= 2.4 -> ceil
		// 3, plus the default overscan of 2 rows = 5 visible rows -> 20 cards.
		expect(screen.getByText('Recording 0')).toBeInTheDocument();
		expect(screen.getByText('Recording 19')).toBeInTheDocument();
		expect(screen.queryByText('Recording 20')).not.toBeInTheDocument();
		expect(screen.queryByText('Recording 99')).not.toBeInTheDocument();

		const spacers = container.querySelectorAll<HTMLDivElement>('.grid-spacer');
		expect(spacers).toHaveLength(2);
		expect(spacers[0].style.height).toBe('0px');
		// 25 total rows - 5 visible = 20 rows skipped below, at 414px each.
		expect(spacers[1].style.height).toBe('8280px');
	});

	it('shifts the window down, and grows the top spacer, once scrolled past the first rows', () => {
		// Same 752px/4-column layout, but the grid has scrolled 3000px past
		// the top of the viewport.
		stubLayout({ clientWidthPx: 752, gridTopPx: -3000, innerHeightPx: 500 });

		const items = Array.from({ length: 100 }, (_, i) => makeRecording(i));
		render(VirtualizedRecordingGrid, {
			props: {
				items,
				failedImages: {},
				deletingRecordingId: null,
				onImageError: noop,
				onPlay: noop,
				onPopout: noop,
				onDelete: noop,
			},
		});

		// 3000/414 ~= 7.2 -> floor 7, minus overscan 2 = row 5 is the first
		// rendered row = item index 20.
		expect(screen.queryByText('Recording 19')).not.toBeInTheDocument();
		expect(screen.getByText('Recording 20')).toBeInTheDocument();
	});
});
