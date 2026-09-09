import { describe, expect, it } from 'vitest';
import { getCategoryType } from './recording-category';
import type { HDHomeRunRecording } from './api';

describe('recording-category', () => {
	function makeRec(overrides: Partial<HDHomeRunRecording> = {}): HDHomeRunRecording {
		return {
			recording_id: 'rec-1',
			title: 'Regular Show',
			start_time: 1000,
			duration: 3600,
			...overrides,
		};
	}

	it('respects existing category_type override when present', () => {
		expect(getCategoryType(makeRec({ category_type: 'movies' }))).toBe('movies');
		expect(getCategoryType(makeRec({ category_type: 'sports' }))).toBe('sports');
		expect(getCategoryType(makeRec({ category_type: 'shows' }))).toBe('shows');
	});

	it('detects sports from category keyword', () => {
		expect(getCategoryType(makeRec({ category: 'Live Football' }))).toBe('sports');
		expect(getCategoryType(makeRec({ category: 'Basketball League' }))).toBe('sports');
	});

	it('detects sports from matchup patterns in episode_title', () => {
		expect(getCategoryType(makeRec({ episode_title: 'Cowboys vs. Eagles' }))).toBe('sports');
		expect(getCategoryType(makeRec({ episode_title: 'Lakers at Celtics' }))).toBe('sports');
		expect(getCategoryType(makeRec({ episode_title: 'Chiefs @ Raiders' }))).toBe('sports');
	});

	it('detects movies from title or category keywords', () => {
		expect(getCategoryType(makeRec({ category: 'Feature Film' }))).toBe('movies');
		expect(getCategoryType(makeRec({ title: 'A Cinema Classic: The Movie' }))).toBe('movies');
	});

	it('defaults to shows when neither sports nor movie matches', () => {
		expect(getCategoryType(makeRec({ title: 'The Evening News', category: 'News' }))).toBe('shows');
	});
});
