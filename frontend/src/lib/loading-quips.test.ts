import { describe, it, expect } from 'vitest';
import { DEFAULT_LOADING_QUIPS, getNextLoadingQuip } from './loading-quips';

describe('loading-quips', () => {
	it('contains a rich catalog of humorous quips', () => {
		expect(DEFAULT_LOADING_QUIPS.length).toBeGreaterThanOrEqual(20);
		for (const quip of DEFAULT_LOADING_QUIPS) {
			expect(typeof quip).toBe('string');
			expect(quip.trim().length).toBeGreaterThan(0);
		}
	});

	it('returns a valid quip when called with no previous quip', () => {
		const quip = getNextLoadingQuip();
		expect(DEFAULT_LOADING_QUIPS).toContain(quip);
	});

	it('avoids immediately repeating the previous quip when options are available', () => {
		const previous = DEFAULT_LOADING_QUIPS[0];
		// Run multiple times to verify exclusion holds
		for (let i = 0; i < 20; i++) {
			const next = getNextLoadingQuip(previous);
			expect(next).not.toBe(previous);
			expect(DEFAULT_LOADING_QUIPS).toContain(next);
		}
	});

	it('handles single-item or empty pools gracefully', () => {
		expect(getNextLoadingQuip(undefined, ['Single quip…'])).toBe('Single quip…');
		expect(getNextLoadingQuip('Single quip…', ['Single quip…'])).toBe('Single quip…');
		expect(getNextLoadingQuip(undefined, [])).toBe('Loading…');
	});
});
