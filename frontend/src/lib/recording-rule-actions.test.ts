import { describe, expect, it } from 'vitest';
import {
	buildEpisodeRulePayload,
	buildSeriesRulePayload,
	buildUpdateRulePayload,
	findNewFallbackRule,
} from './recording-rule-actions';
import type { HDHomeRunRecordingRule } from './api';

describe('recording-rule-actions', () => {
	it('builds episode rule payload correctly', () => {
		const payload = buildEpisodeRulePayload({
			seriesId: 'series-1',
			channel: '4.1',
			startTime: 1234567,
			options: {
				title: 'Special Episode',
				startPadding: 60,
				endPadding: 120,
				recentOnly: true,
				maxEpisodesToKeep: 5,
				server: 'builtin',
			},
		});

		expect(payload).toEqual({
			series_id: 'series-1',
			channel: '4.1',
			date_time: 1234567,
			title: 'Special Episode',
			start_padding: 60,
			end_padding: 120,
			recent_only: true,
			max_episodes_to_keep: 5,
			server: 'builtin',
		});
	});

	it('buildEpisodeRulePayload falls back to auto series_id and options channel override', () => {
		const payload = buildEpisodeRulePayload({
			channel: '4.1',
			options: {
				channel: '5.1',
			},
		});

		expect(payload.series_id).toBe('auto');
		expect(payload.channel).toBe('5.1');
		expect(payload.date_time).toBeUndefined();
	});

	it('builds series rule payload with title match mode and keyword query', () => {
		const payload = buildSeriesRulePayload({
			seriesId: 'series-2',
			channel: '7.1',
			options: {
				title: 'Morning News',
				titleMatchMode: 'exact',
				keywordQuery: 'weather',
				recentOnly: false,
			},
		});

		expect(payload).toEqual({
			series_id: 'series-2',
			channel: '7.1',
			title: 'Morning News',
			title_match_mode: 'exact',
			keyword_query: 'weather',
			start_padding: undefined,
			end_padding: undefined,
			recent_only: false,
			max_episodes_to_keep: undefined,
			server: undefined,
		});
	});

	it('builds update rule payload with options', () => {
		const payload = buildUpdateRulePayload({
			channel: '11.1',
			title: 'Nightly Movie',
			maxEpisodesToKeep: 3,
		});

		expect(payload).toEqual({
			channel: '11.1',
			title: 'Nightly Movie',
			title_match_mode: undefined,
			keyword_query: undefined,
			start_padding: undefined,
			end_padding: undefined,
			recent_only: undefined,
			max_episodes_to_keep: 3,
			server: undefined,
		});
	});

	it('findNewFallbackRule returns newly created fallback rule', () => {
		const oldRules: HDHomeRunRecordingRule[] = [
			{ RecordingRuleID: 'r1', SeriesID: 's1', Title: 'Rule 1' },
		];
		const updatedRules: HDHomeRunRecordingRule[] = [
			{ RecordingRuleID: 'r1', SeriesID: 's1', Title: 'Rule 1' },
			{ RecordingRuleID: 'r2', SeriesID: 's2', Title: 'Rule 2', fallback_reason: 'Tuner occupied' },
		];

		const fallback = findNewFallbackRule(oldRules, updatedRules);
		expect(fallback?.RecordingRuleID).toBe('r2');
	});

	it('findNewFallbackRule returns null when no new fallback rule exists', () => {
		const oldRules: HDHomeRunRecordingRule[] = [
			{ RecordingRuleID: 'r1', SeriesID: 's1', Title: 'Rule 1' },
		];
		const updatedRules: HDHomeRunRecordingRule[] = [
			{ RecordingRuleID: 'r1', SeriesID: 's1', Title: 'Rule 1' },
			{ RecordingRuleID: 'r2', SeriesID: 's2', Title: 'Rule 2' },
		];

		const fallback = findNewFallbackRule(oldRules, updatedRules);
		expect(fallback).toBeNull();
	});
});
