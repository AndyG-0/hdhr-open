import { describe, expect, it } from 'vitest';
import type { HDHomeRunRecordingRule } from '$lib/api';
import { buildRecordingRuleIndex, findMatchingRecordingRule, findMatchingRecordingRuleIndexed } from './recording-rules';

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

describe('findMatchingRecordingRuleIndexed', () => {
	function find(
		rules: HDHomeRunRecordingRule[],
		channelNumber: string | undefined,
		airing: Parameters<typeof findMatchingRecordingRule>[2],
	) {
		return findMatchingRecordingRuleIndexed(buildRecordingRuleIndex(rules), channelNumber, airing);
	}

	it('returns null when there are no rules', () => {
		expect(find([], '5.1', { series_id: 'series-1' })).toBeNull();
		expect(findMatchingRecordingRuleIndexed(buildRecordingRuleIndex(undefined), '5.1', { series_id: 'series-1' })).toBeNull();
	});

	it('matches a ChannelOnly pipe-list rule by channel number (still requires a SeriesID/DateTimeOnly match)', () => {
		const r = rule({ ChannelOnly: '5.1|5.2', SeriesID: 'series-1' });
		expect(find([r], '5.1', { series_id: 'series-1' })).toBe(r);
		expect(find([r], '5.2', { series_id: 'series-1' })).toBe(r);
		expect(find([r], '9.1', { series_id: 'series-1' })).toBeNull();
		expect(find([r], '5.1', { series_id: 'unrelated' })).toBeNull();
	});

	it('matches a DateTimeOnly rule within a 60s window, straddling minute-bucket boundaries', () => {
		const r = rule({ DateTimeOnly: 1000, SeriesID: undefined });
		expect(find([r], undefined, { start: 1000 + 59 })).toBe(r);
		expect(find([r], undefined, { start: 1000 - 59 })).toBe(r);
		expect(find([r], undefined, { start: 1000 + 60 })).toBeNull();
		expect(find([r], undefined, { start: 1000 + 61 })).toBeNull();
	});

	it('does not fall back to SeriesID matching when DateTimeOnly is set but the airing has no start', () => {
		const r = rule({ DateTimeOnly: 1000, SeriesID: 'series-1' });
		expect(find([r], undefined, { series_id: 'series-1', start: null })).toBeNull();
	});

	it('falls back to matching by SeriesID', () => {
		const r = rule({ SeriesID: 'series-1' });
		expect(find([r], undefined, { series_id: 'series-1' })).toBe(r);
		expect(find([r], undefined, { series_id: 'other' })).toBeNull();
	});

	it('first-wins ordering: an earlier rule beats a later one sharing the same channel+minute key', () => {
		const first = rule({ RecordingRuleID: 'rule-first', DateTimeOnly: 1000, SeriesID: undefined, ChannelOnly: '5.1' });
		const second = rule({ RecordingRuleID: 'rule-second', DateTimeOnly: 1000, SeriesID: undefined, ChannelOnly: '5.1' });
		expect(find([first, second], '5.1', { start: 1000 })).toBe(first);
		expect(find([second, first], '5.1', { start: 1000 })).toBe(second);
	});

	it('first-wins ordering across rule types: a later SeriesID rule loses to an earlier DateTimeOnly rule matching the same airing', () => {
		const timeRule = rule({ RecordingRuleID: 'time-rule', DateTimeOnly: 1000, SeriesID: undefined });
		const seriesRule = rule({ RecordingRuleID: 'series-rule', SeriesID: 'series-1' });
		const airing = { start: 1000, series_id: 'series-1' };

		expect(find([timeRule, seriesRule], undefined, airing)).toBe(timeRule);
		expect(find([seriesRule, timeRule], undefined, airing)).toBe(seriesRule);
	});

	it('matches the original findMatchingRecordingRule behavior across a mixed rule set', () => {
		const rules = [
			rule({ RecordingRuleID: 'r1', ChannelOnly: '5.1', DateTimeOnly: 2000, SeriesID: undefined }),
			rule({ RecordingRuleID: 'r2', SeriesID: 'series-2' }),
			rule({ RecordingRuleID: 'r3', ChannelOnly: '9.1|9.2', SeriesID: 'series-3' }),
		];
		const cases: [string | undefined, Parameters<typeof findMatchingRecordingRule>[2]][] = [
			['5.1', { start: 2000 }],
			['5.1', { start: 2100 }],
			[undefined, { series_id: 'series-2' }],
			['9.2', { series_id: 'series-3' }],
			['9.9', { series_id: 'series-3' }],
		];
		for (const [channel, airing] of cases) {
			expect(find(rules, channel, airing)).toBe(findMatchingRecordingRule(rules, channel, airing));
		}
	});
});
