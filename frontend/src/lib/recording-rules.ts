import type { HDHomeRunRecordingRule } from '$lib/api';

/** Minimal shape of a guide airing this predicate needs to match against. */
interface MatchableAiring {
	start?: number | null;
	series_id?: string | null;
}

/**
 * Finds the recording rule (if any) that covers a given channel/airing.
 * `ChannelOnly` rules match by channel number; `DateTimeOnly` rules match a
 * specific airing's start time (within a minute, to absorb schedule drift);
 * everything else falls back to matching by series ID.
 */
export function findMatchingRecordingRule(
	rules: HDHomeRunRecordingRule[] | undefined,
	channelNumber: string | undefined,
	airing: MatchableAiring | null | undefined,
): HDHomeRunRecordingRule | null {
	if (!rules || rules.length === 0) return null;
	return (
		rules.find((r) => {
			const channelMatches = !r.ChannelOnly || (channelNumber && r.ChannelOnly.split('|').includes(channelNumber));
			if (!channelMatches) return false;
			if (r.DateTimeOnly != null) {
				return airing?.start != null && Math.abs(r.DateTimeOnly - airing.start) < 60;
			}
			return !!(r.SeriesID && airing?.series_id && r.SeriesID === airing.series_id);
		}) ?? null
	);
}

/**
 * A pre-built lookup structure equivalent to {@link findMatchingRecordingRule}
 * but O(1) per query instead of O(rules.length) — for guide grids that call
 * the matcher once per rendered airing cell. Build once per `rules` array
 * (e.g. via `$derived.by`) and reuse across every cell/channel lookup.
 */
export interface RecordingRuleIndex {
	byChannelMinute: Map<string, HDHomeRunRecordingRule>;
	byMinuteAnyChannel: Map<number, HDHomeRunRecordingRule>;
	byChannelSeries: Map<string, HDHomeRunRecordingRule>;
	bySeriesAnyChannel: Map<string, HDHomeRunRecordingRule>;
	/** Original array position per rule, used to break ties the same way `Array.find` would. */
	order: Map<string, number>;
}

export function buildRecordingRuleIndex(rules: HDHomeRunRecordingRule[] | undefined): RecordingRuleIndex {
	const index: RecordingRuleIndex = {
		byChannelMinute: new Map(),
		byMinuteAnyChannel: new Map(),
		byChannelSeries: new Map(),
		bySeriesAnyChannel: new Map(),
		order: new Map(),
	};
	if (!rules) return index;

	rules.forEach((rule, i) => {
		index.order.set(rule.RecordingRuleID, i);
		const channels = rule.ChannelOnly ? rule.ChannelOnly.split('|') : [null];

		if (rule.DateTimeOnly != null) {
			const minute = Math.floor(rule.DateTimeOnly / 60);
			for (const channel of channels) {
				if (channel === null) {
					if (!index.byMinuteAnyChannel.has(minute)) index.byMinuteAnyChannel.set(minute, rule);
				} else {
					const key = `${channel}:${minute}`;
					if (!index.byChannelMinute.has(key)) index.byChannelMinute.set(key, rule);
				}
			}
		} else if (rule.SeriesID) {
			for (const channel of channels) {
				if (channel === null) {
					if (!index.bySeriesAnyChannel.has(rule.SeriesID)) index.bySeriesAnyChannel.set(rule.SeriesID, rule);
				} else {
					const key = `${channel}:${rule.SeriesID}`;
					if (!index.byChannelSeries.has(key)) index.byChannelSeries.set(key, rule);
				}
			}
		}
		// Rules with neither DateTimeOnly nor a truthy SeriesID never match anything (matches the original's implicit behavior).
	});

	return index;
}

export function findMatchingRecordingRuleIndexed(
	index: RecordingRuleIndex,
	channelNumber: string | undefined,
	airing: MatchableAiring | null | undefined,
): HDHomeRunRecordingRule | null {
	let best: HDHomeRunRecordingRule | null = null;
	let bestOrder = Infinity;

	// Multiple index buckets can each produce a candidate for the same airing
	// (e.g. a DateTimeOnly rule and a SeriesID rule); track original array
	// order so the earliest-in-array candidate wins, same as Array.find.
	function consider(candidate: HDHomeRunRecordingRule | undefined) {
		if (!candidate) return;
		const order = index.order.get(candidate.RecordingRuleID) ?? Infinity;
		if (order < bestOrder) {
			best = candidate;
			bestOrder = order;
		}
	}

	if (airing?.start != null) {
		const minute = Math.floor(airing.start / 60);
		for (const bucket of [minute - 1, minute, minute + 1]) {
			if (channelNumber) {
				const candidate = index.byChannelMinute.get(`${channelNumber}:${bucket}`);
				if (candidate && Math.abs(candidate.DateTimeOnly! - airing.start) < 60) consider(candidate);
			}
			const candidateAnyChannel = index.byMinuteAnyChannel.get(bucket);
			if (candidateAnyChannel && Math.abs(candidateAnyChannel.DateTimeOnly! - airing.start) < 60) {
				consider(candidateAnyChannel);
			}
		}
	}

	if (airing?.series_id) {
		if (channelNumber) {
			consider(index.byChannelSeries.get(`${channelNumber}:${airing.series_id}`));
		}
		consider(index.bySeriesAnyChannel.get(airing.series_id));
	}

	return best;
}
