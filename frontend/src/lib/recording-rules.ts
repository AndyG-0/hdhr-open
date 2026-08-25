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
