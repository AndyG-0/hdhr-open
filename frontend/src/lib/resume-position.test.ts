import { describe, expect, it, beforeEach, vi, afterEach } from 'vitest';
import {
	clearResumePosition,
	getResumePosition,
	resumeKeyFor,
	saveResumePosition,
} from './resume-position';

describe('resume-position', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('prefers recordingId, falls back to playUrl', () => {
		expect(resumeKeyFor({ recordingId: 'r1', playUrl: 'u' })).toBe('r1');
		expect(resumeKeyFor({ recordingId: null, playUrl: 'u' })).toBe('u');
		expect(resumeKeyFor({})).toBeNull();
	});

	it('round-trips a mid-recording position', () => {
		saveResumePosition('r1', 600, 3600);
		expect(getResumePosition('r1', 3600)).toBe(600);
		expect(getResumePosition('other', 3600)).toBeNull();
	});

	it('uses the stored duration when the current one is unknown', () => {
		saveResumePosition('r1', 3590, 3600);
		// Already cleared on save as "finished"
		expect(getResumePosition('r1', null)).toBeNull();
		saveResumePosition('r2', 600, 3600);
		expect(getResumePosition('r2', null)).toBe(600);
	});

	it('does not resume a barely-started recording, and clears an existing entry', () => {
		saveResumePosition('r1', 600, 3600);
		saveResumePosition('r1', 5, 3600);
		expect(getResumePosition('r1', 3600)).toBeNull();
	});

	it('treats the last minute / last 5% as finished', () => {
		saveResumePosition('r1', 3550, 3600);
		expect(getResumePosition('r1', 3600)).toBeNull();
		saveResumePosition('r2', 580, 600); // 96.7%
		expect(getResumePosition('r2', 600)).toBeNull();
	});

	it('clears an entry explicitly', () => {
		saveResumePosition('r1', 600, 3600);
		clearResumePosition('r1');
		expect(getResumePosition('r1', 3600)).toBeNull();
	});

	it('prunes to the 200 most recently updated entries', () => {
		const now = vi.spyOn(Date, 'now');
		for (let i = 0; i < 205; i++) {
			now.mockReturnValue(1_000 + i);
			saveResumePosition(`r${i}`, 600, 3600);
		}
		const stored = JSON.parse(localStorage.getItem('hdhr_resume_positions')!);
		expect(Object.keys(stored)).toHaveLength(200);
		expect(stored.r0).toBeUndefined();
		expect(stored.r204).toBeDefined();
	});

	it('survives corrupt or throwing storage', () => {
		localStorage.setItem('hdhr_resume_positions', '{not json');
		expect(getResumePosition('r1', 3600)).toBeNull();
		vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
			throw new Error('quota');
		});
		expect(() => saveResumePosition('r1', 600, 3600)).not.toThrow();
	});
});
