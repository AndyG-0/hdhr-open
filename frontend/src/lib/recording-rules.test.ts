import { describe, expect, it } from 'vitest';
import type { HDHomeRunRecordingRule } from '$lib/api';
import { findMatchingRecordingRule } from './recording-rules';

function rule(overrides: Partial<HDHomeRunRecordingRule>): HDHomeRunRecordingRule {
	return {
		RecordingRuleID: 'rule-1',
		SeriesID: 'series-1',
		Title: 'Test Show',
		...overrides,
	};
}

describe('findMatchingRecordingRule', () => {
	it('returns null when there are no rules', () => {
		expect(findMatchingRecordingRule(undefined, '5.1', { series_id: 'series-1' })).toBeNull();
		expect(findMatchingRecordingRule([], '5.1', { series_id: 'series-1' })).toBeNull();
	});

	it('matches a ChannelOnly rule by channel number (still requires a SeriesID/DateTimeOnly match)', () => {
		const r = rule({ ChannelOnly: '5.1|5.2', SeriesID: 'series-1' });
		expect(findMatchingRecordingRule([r], '5.1', { series_id: 'series-1' })).toBe(r);
		expect(findMatchingRecordingRule([r], '9.1', { series_id: 'series-1' })).toBeNull();
		expect(findMatchingRecordingRule([r], '5.1', { series_id: 'unrelated' })).toBeNull();
	});

	it('matches a DateTimeOnly rule within a 60s window', () => {
		const r = rule({ DateTimeOnly: 1000 });
		expect(findMatchingRecordingRule([r], undefined, { start: 1030 })).toBe(r);
		expect(findMatchingRecordingRule([r], undefined, { start: 1090 })).toBeNull();
	});

	it('does not fall back to SeriesID matching when DateTimeOnly is set but the airing has no start', () => {
		const r = rule({ DateTimeOnly: 1000, SeriesID: 'series-1' });
		expect(findMatchingRecordingRule([r], undefined, { series_id: 'series-1', start: null })).toBeNull();
	});

	it('falls back to matching by SeriesID', () => {
		const r = rule({ SeriesID: 'series-1' });
		expect(findMatchingRecordingRule([r], undefined, { series_id: 'series-1' })).toBe(r);
		expect(findMatchingRecordingRule([r], undefined, { series_id: 'other' })).toBeNull();
	});
});
