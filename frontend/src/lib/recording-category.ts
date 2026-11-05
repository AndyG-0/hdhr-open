import type { HDHomeRunRecording } from '$lib/api';

export const SPORTS_KEYWORDS = [
	'sport',
	'sports',
	'football',
	'basketball',
	'baseball',
	'hockey',
	'soccer',
	'golf',
	'tennis',
	'racing',
	'nascar',
	'formula 1',
	'f1',
	'olympics',
	'wrestling',
	'boxing',
	'mma',
	'ufc',
	'wwe',
	'nfl',
	'nba',
	'mlb',
	'nhl',
	'pga',
	'mls',
	'premier league',
	'champions league',
	'uefa',
	'fifa',
	'ncaa',
	'college football',
	'college basketball',
];

export const MOVIE_KEYWORDS = ['movie', 'feature film', 'film', 'cinema'];

export type RecordingCategoryType = 'shows' | 'movies' | 'sports';

/**
 * Classifies a recording into shows, movies, or sports using category_type metadata
 * or title/episode/synopsis heuristic matching.
 */
export function getCategoryType(rec: HDHomeRunRecording): RecordingCategoryType {
	if (rec.category_type) return rec.category_type;
	const t = (rec.title || '').toLowerCase();
	const ep = (rec.episode_title || '').toLowerCase();
	const cat = (rec.category || '').toLowerCase();

	if (
		SPORTS_KEYWORDS.some((k) => cat.includes(k) || t.includes(k)) ||
		ep.includes(' at ') ||
		ep.includes(' vs ') ||
		ep.includes(' vs. ') ||
		ep.includes(' @ ')
	) {
		return 'sports';
	}

	if (MOVIE_KEYWORDS.some((k) => cat.includes(k) || t.includes(k))) {
		return 'movies';
	}

	return 'shows';
}

/**
 * Splits a comma-separated category string into trimmed, non-empty tags.
 * Repeats are dropped (case-insensitive, first spelling wins) so the tags can
 * be used as each-block keys.
 */
export function splitCategoryTags(category: string | null | undefined): string[] {
	if (!category) return [];
	const seen = new Set<string>();
	const tags: string[] = [];
	for (const raw of category.split(',')) {
		const tag = raw.trim();
		const key = tag.toLowerCase();
		if (!tag || seen.has(key)) continue;
		seen.add(key);
		tags.push(tag);
	}
	return tags;
}
