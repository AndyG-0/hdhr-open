import type { HDHomeRunRecordingRule } from '$lib/api';

/** Minimal shape of a guide airing this predicate needs to match against. */
interface MatchableAiring {
	start?: number | null;
	series_id?: string | null;
	title?: string | null;
	episode_title?: string | null;
	synopsis?: string | null;
	category?: string | null;
}

function normalize(s: string): string {
	return s.trim().toLowerCase().replace(/\s+/g, ' ');
}

/** Mirrors the backend's rule_expander._title_matches - exact or substring. */
function titleMatches(ruleTitle: string, airingTitle: string | null | undefined, mode: string | undefined): boolean {
	if (!ruleTitle || !airingTitle) return false;
	const normRule = normalize(ruleTitle);
	const normAiring = normalize(airingTitle);
	return mode === 'contains' ? normAiring.includes(normRule) : normRule === normAiring;
}

/** Mirrors the backend's rule_expander._keyword_matches inclusion filter. */
function keywordMatches(keywordQuery: string | null | undefined, airing: MatchableAiring): boolean {
	if (!keywordQuery) return true;
	const terms = keywordQuery
		.split(',')
		.map((t) => t.trim())
		.filter(Boolean)
		.map(normalize);
	if (terms.length === 0) return true;
	const haystacks = [airing.episode_title, airing.synopsis, airing.category, airing.title].filter(
		(v): v is string => !!v,
	).map(normalize);
	return terms.some((term) => haystacks.some((h) => h.includes(term)));
}

/** True for a rule that uses substring title matching and/or a keyword filter. */
function isKeywordRule(r: HDHomeRunRecordingRule): boolean {
	return r.TitleMatchMode === 'contains' || !!r.KeywordQuery;
}

function keywordRuleMatchesAiring(r: HDHomeRunRecordingRule, channelNumber: string | undefined, airing: MatchableAiring | null | undefined): boolean {
	const channelMatches = !r.ChannelOnly || (channelNumber && r.ChannelOnly.split('|').includes(channelNumber));
	if (!channelMatches || !airing) return false;
	const seriesMatches = !!(r.SeriesID && airing.series_id && r.SeriesID === airing.series_id);
	const titleMatchesAiring = titleMatches(r.Title, airing.title, r.TitleMatchMode);
	if (!seriesMatches && !titleMatchesAiring) return false;
	return keywordMatches(r.KeywordQuery, airing);
}

/**
 * Finds the recording rule (if any) that covers a given channel/airing.
 * `ChannelOnly` rules match by channel number; `DateTimeOnly` rules match a
 * specific airing's start time (within a minute, to absorb schedule drift);
 * a keyword/contains rule matches by title (exact or substring) AND'd with
 * an optional keyword filter against episode_title/synopsis/title; everything
 * else falls back to matching by series ID.
 */
export function findMatchingRecordingRule(
	rules: HDHomeRunRecordingRule[] | undefined,
	channelNumber: string | undefined,
	airing: MatchableAiring | null | undefined,
): HDHomeRunRecordingRule | null {
	if (!rules || rules.length === 0 || !airing) return null;
	return (
		rules.find((r) => {
			const channelMatches = !r.ChannelOnly || (channelNumber && r.ChannelOnly.split('|').includes(channelNumber));
			if (!channelMatches) return false;
			if (isKeywordRule(r)) {
				return keywordRuleMatchesAiring(r, channelNumber, airing);
			}
			if (r.DateTimeOnly != null) {
				return airing.start != null && Math.abs(r.DateTimeOnly - airing.start) < 60;
			}
			const seriesMatches = !!(r.SeriesID && airing.series_id && r.SeriesID === airing.series_id);
			const titleMatchesAiring = titleMatches(r.Title, airing.title, r.TitleMatchMode);
			return seriesMatches || titleMatchesAiring;
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
	byChannelTitle: Map<string, HDHomeRunRecordingRule>;
	byTitleAnyChannel: Map<string, HDHomeRunRecordingRule>;
	/** Keyword/contains rules can't be hashed by exact title or series ID, so
	 * they're checked via a linear scan after the O(1) lookups miss. Expected
	 * to be rare (whole-topic standing rules, not one per episode). */
	keywordRules: HDHomeRunRecordingRule[];
	/** Original array position per rule, used to break ties the same way `Array.find` would. */
	order: Map<string, number>;
}

export function buildRecordingRuleIndex(rules: HDHomeRunRecordingRule[] | undefined): RecordingRuleIndex {
	const index: RecordingRuleIndex = {
		byChannelMinute: new Map(),
		byMinuteAnyChannel: new Map(),
		byChannelSeries: new Map(),
		bySeriesAnyChannel: new Map(),
		byChannelTitle: new Map(),
		byTitleAnyChannel: new Map(),
		keywordRules: [],
		order: new Map(),
	};
	if (!rules) return index;

	rules.forEach((rule, i) => {
		index.order.set(rule.RecordingRuleID, i);

		if (isKeywordRule(rule)) {
			index.keywordRules.push(rule);
			return;
		}

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
		} else {
			if (rule.SeriesID) {
				for (const channel of channels) {
					if (channel === null) {
						if (!index.bySeriesAnyChannel.has(rule.SeriesID)) index.bySeriesAnyChannel.set(rule.SeriesID, rule);
					} else {
						const key = `${channel}:${rule.SeriesID}`;
						if (!index.byChannelSeries.has(key)) index.byChannelSeries.set(key, rule);
					}
				}
			}
			if (rule.Title) {
				const normTitle = normalize(rule.Title);
				if (normTitle) {
					for (const channel of channels) {
						if (channel === null) {
							if (!index.byTitleAnyChannel.has(normTitle)) index.byTitleAnyChannel.set(normTitle, rule);
						} else {
							const key = `${channel}:${normTitle}`;
							if (!index.byChannelTitle.has(key)) index.byChannelTitle.set(key, rule);
						}
					}
				}
			}
		}
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

	if (airing?.title) {
		const normTitle = normalize(airing.title);
		if (normTitle) {
			if (channelNumber) {
				consider(index.byChannelTitle.get(`${channelNumber}:${normTitle}`));
			}
			consider(index.byTitleAnyChannel.get(normTitle));
		}
	}

	for (const rule of index.keywordRules) {
		if (keywordRuleMatchesAiring(rule, channelNumber, airing)) consider(rule);
	}

	return best;
}
