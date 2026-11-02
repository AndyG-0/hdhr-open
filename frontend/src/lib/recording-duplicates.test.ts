import { describe, expect, it } from 'vitest';
import type { HDHomeRunRecording, HDHomeRunRecordingDuplicateGroup } from '$lib/api';
import { groupsWithAllSelected, initialSelection, selectionSummary } from './recording-duplicates';

function rec(id: string, size: number | null = 100): HDHomeRunRecording {
	return {
		recording_id: id,
		title: 'Jeopardy!',
		channel_name: 'WNBC',
		start: 1000,
		record_end: 2000,
		file_size_bytes: size,
	};
}

const groups: HDHomeRunRecordingDuplicateGroup[] = [
	{
		key: 'g1',
		title: 'Jeopardy!',
		episode_title: 'Game 1',
		category_type: 'shows',
		suggested_keep_id: 'a2',
		recordings: [rec('a1'), rec('a2'), rec('a3', null)],
	},
	{
		key: 'g2',
		title: 'Casablanca',
		episode_title: null,
		category_type: 'movies',
		suggested_keep_id: 'b1',
		recordings: [rec('b1'), rec('b2', 500)],
	},
];

describe('initialSelection', () => {
	it('checks everything except each suggested keeper', () => {
		expect([...initialSelection(groups)].sort()).toEqual(['a1', 'a3', 'b2']);
	});
});

describe('groupsWithAllSelected', () => {
	it('is empty for the initial selection', () => {
		expect(groupsWithAllSelected(groups, initialSelection(groups)).size).toBe(0);
	});

	it('flags groups where every copy is checked', () => {
		const selected = new Set(['a1', 'a2', 'a3', 'b2']);
		expect([...groupsWithAllSelected(groups, selected)]).toEqual(['g1']);
	});
});

describe('selectionSummary', () => {
	it('counts checked recordings and sums their sizes', () => {
		expect(selectionSummary(groups, initialSelection(groups))).toEqual({ count: 3, bytes: 600 });
	});

	it('ignores unknown ids', () => {
		expect(selectionSummary(groups, new Set(['zzz']))).toEqual({ count: 0, bytes: 0 });
	});
});
