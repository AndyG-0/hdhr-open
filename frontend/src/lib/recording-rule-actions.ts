import type { HDHomeRunRecordingRule, RecordingRuleOptions } from '$lib/api';

export interface EpisodeRulePayloadParams {
	seriesId?: string | null;
	channel?: string;
	startTime?: number | null;
	options?: RecordingRuleOptions;
}

export function buildEpisodeRulePayload(
	paramsOrSeriesId?: EpisodeRulePayloadParams | string | null,
	channelNumber?: string,
	startTime?: number | null,
	options?: RecordingRuleOptions,
) {
	if (paramsOrSeriesId && typeof paramsOrSeriesId === 'object') {
		const effectiveOptions = paramsOrSeriesId.options ?? {};
		const effectiveChannel = effectiveOptions.channel !== undefined ? effectiveOptions.channel : paramsOrSeriesId.channel;
		return {
			series_id: paramsOrSeriesId.seriesId || 'auto',
			channel: effectiveChannel,
			date_time: paramsOrSeriesId.startTime ?? undefined,
			title: effectiveOptions.title,
			start_padding: effectiveOptions.startPadding,
			end_padding: effectiveOptions.endPadding,
			recent_only: effectiveOptions.recentOnly,
			max_episodes_to_keep: effectiveOptions.maxEpisodesToKeep,
			server: effectiveOptions.server,
		};
	}

	const effectiveOptions = options ?? {};
	const effectiveChannel = effectiveOptions.channel !== undefined ? effectiveOptions.channel : channelNumber;
	return {
		series_id: paramsOrSeriesId || 'auto',
		channel: effectiveChannel,
		date_time: startTime ?? undefined,
		title: effectiveOptions.title,
		start_padding: effectiveOptions.startPadding,
		end_padding: effectiveOptions.endPadding,
		recent_only: effectiveOptions.recentOnly,
		max_episodes_to_keep: effectiveOptions.maxEpisodesToKeep,
		server: effectiveOptions.server,
	};
}

export interface SeriesRulePayloadParams {
	seriesId?: string | null;
	channel?: string;
	options?: RecordingRuleOptions;
}

export function buildSeriesRulePayload(
	paramsOrSeriesId?: SeriesRulePayloadParams | string | null,
	channelNumber?: string,
	options?: RecordingRuleOptions,
) {
	if (paramsOrSeriesId && typeof paramsOrSeriesId === 'object') {
		const effectiveOptions = paramsOrSeriesId.options ?? {};
		const effectiveChannel = effectiveOptions.channel !== undefined ? effectiveOptions.channel : paramsOrSeriesId.channel;
		return {
			series_id: paramsOrSeriesId.seriesId || 'auto',
			channel: effectiveChannel,
			title: effectiveOptions.title,
			title_match_mode: effectiveOptions.titleMatchMode,
			keyword_query: effectiveOptions.keywordQuery,
			start_padding: effectiveOptions.startPadding,
			end_padding: effectiveOptions.endPadding,
			recent_only: effectiveOptions.recentOnly,
			max_episodes_to_keep: effectiveOptions.maxEpisodesToKeep,
			server: effectiveOptions.server,
		};
	}

	const effectiveOptions = options ?? {};
	const effectiveChannel = effectiveOptions.channel !== undefined ? effectiveOptions.channel : channelNumber;
	return {
		series_id: paramsOrSeriesId || 'auto',
		channel: effectiveChannel,
		title: effectiveOptions.title,
		title_match_mode: effectiveOptions.titleMatchMode,
		keyword_query: effectiveOptions.keywordQuery,
		start_padding: effectiveOptions.startPadding,
		end_padding: effectiveOptions.endPadding,
		recent_only: effectiveOptions.recentOnly,
		max_episodes_to_keep: effectiveOptions.maxEpisodesToKeep,
		server: effectiveOptions.server,
	};
}

export function buildUpdateRulePayload(options: RecordingRuleOptions) {
	return {
		channel: options.channel,
		title: options.title,
		title_match_mode: options.titleMatchMode,
		keyword_query: options.keywordQuery,
		start_padding: options.startPadding,
		end_padding: options.endPadding,
		recent_only: options.recentOnly,
		max_episodes_to_keep: options.maxEpisodesToKeep,
		server: options.server,
	};
}

export function findNewFallbackRule(
	previousRules: HDHomeRunRecordingRule[] | Set<string>,
	updatedRules: HDHomeRunRecordingRule[],
): HDHomeRunRecordingRule | null {
	const previousIds =
		previousRules instanceof Set
			? previousRules
			: new Set(previousRules.map((r) => r.RecordingRuleID));
	const newlyCreated = updatedRules.filter((r) => !previousIds.has(r.RecordingRuleID));
	return newlyCreated.find((r) => r.fallback_reason || r.FallbackReason) ?? null;
}
