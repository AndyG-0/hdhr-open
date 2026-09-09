import {
	api,
	type HDHomeRunGuideEntry,
	type HDHomeRunRecordingRule,
	type RecordingRuleOptions,
} from '$lib/api';
import {
	buildEpisodeRulePayload,
	buildSeriesRulePayload,
	buildUpdateRulePayload,
} from '$lib/recording-rule-actions';

export interface RecordingActionsControllerOptions {
	getEffectiveAiring: () => HDHomeRunGuideEntry | null;
	getChannelName: () => string;
	getChannelNumber: () => string | undefined;
	getIsWatchSession: () => boolean;
	getWatchSessionId: () => string | null | undefined;
	getCurrentRule: () => HDHomeRunRecordingRule | null;
	getRecordingRules: () => HDHomeRunRecordingRule[];
	setRecordingRules: (rules: HDHomeRunRecordingRule[]) => void;
	setErrorMessage: (msg: string | null) => void;
	setInternalRecordingLoading: (loading: boolean) => void;
	setShowRecordMenu: (show: boolean) => void;
	setShowOptionsDialog: (show: boolean) => void;
	getOnRecordEpisode?: () =>
		| ((
				seriesId?: string | null,
				channelNumber?: string,
				start?: number | null,
				options?: RecordingRuleOptions,
		  ) => Promise<void> | void)
		| undefined;
	getOnRecordSeries?: () =>
		| ((
				seriesId: string,
				channelNumber?: string,
				options?: RecordingRuleOptions,
		  ) => Promise<void> | void)
		| undefined;
	getOnCancelRule?: () => ((ruleId: string) => Promise<void> | void) | undefined;
	getOnUpdateRule?: () =>
		| ((
				ruleId: string,
				mode: 'episode' | 'series',
				options: RecordingRuleOptions,
		  ) => Promise<void> | void)
		| undefined;
	onRecordEpisode?: (
		seriesId?: string | null,
		channelNumber?: string,
		start?: number | null,
		options?: RecordingRuleOptions,
	) => Promise<void> | void;
	onRecordSeries?: (
		seriesId: string,
		channelNumber?: string,
		options?: RecordingRuleOptions,
	) => Promise<void> | void;
	onCancelRule?: (ruleId: string) => Promise<void> | void;
	onUpdateRule?: (
		ruleId: string,
		mode: 'episode' | 'series',
		options: RecordingRuleOptions,
	) => Promise<void> | void;
	translate?: (key: string) => string;
}

export interface RecordingActionsController {
	handleRecordEpisode: (options?: RecordingRuleOptions) => Promise<void>;
	handleRecordSeries: (options?: RecordingRuleOptions) => Promise<void>;
	handleCancelRecording: () => Promise<void>;
	handleUpdateRule: (ruleId: string, mode: 'episode' | 'series', options: RecordingRuleOptions) => Promise<void>;
	handleConfirmOptions: (mode: 'episode' | 'series', options: RecordingRuleOptions) => void;
}

export function createRecordingActionsController(
	options: RecordingActionsControllerOptions,
): RecordingActionsController {
	function getErrorText(err: unknown): string {
		if (err instanceof Error && err.message) return err.message;
		return options.translate?.('common.connection_save_error') ?? 'Could not save recording rule';
	}

	async function handleRecordEpisode(ruleOptions?: RecordingRuleOptions): Promise<void> {
		options.setErrorMessage(null);
		options.setShowRecordMenu(false);
		options.setShowOptionsDialog(false);
		options.setInternalRecordingLoading(true);

		const effectiveAiring = options.getEffectiveAiring();
		const channelName = options.getChannelName();
		const channelNumber = options.getChannelNumber();
		const effectiveOptions: RecordingRuleOptions = {
			title: effectiveAiring?.title ?? channelName,
			...ruleOptions,
		};
		const targetChannel = effectiveOptions.channel !== undefined ? effectiveOptions.channel : channelNumber;

		try {
			if (options.getIsWatchSession() && options.getWatchSessionId()) {
				await api.promoteWatch(options.getWatchSessionId()!, {
					title: effectiveAiring?.title ?? channelName,
					episode_title: effectiveAiring?.episode_title ?? undefined,
				});
				return;
			}

			const onRecordEpisode = options.getOnRecordEpisode ? options.getOnRecordEpisode() : options.onRecordEpisode;
			if (onRecordEpisode) {
				await onRecordEpisode(
					effectiveAiring?.series_id,
					targetChannel,
					effectiveAiring?.start,
					effectiveOptions,
				);
			} else {
				const payload = buildEpisodeRulePayload({
					seriesId: effectiveAiring?.series_id,
					channel: targetChannel,
					startTime: effectiveAiring?.start,
					options: effectiveOptions,
				});
				const updatedRules = await api.addHDHomeRunRecordingRule(payload);
				if (Array.isArray(updatedRules)) {
					options.setRecordingRules(updatedRules);
				}
			}
		} catch (err) {
			options.setErrorMessage(getErrorText(err));
		} finally {
			options.setInternalRecordingLoading(false);
		}
	}

	async function handleRecordSeries(ruleOptions?: RecordingRuleOptions): Promise<void> {
		options.setErrorMessage(null);
		options.setShowRecordMenu(false);
		options.setShowOptionsDialog(false);
		options.setInternalRecordingLoading(true);

		const effectiveAiring = options.getEffectiveAiring();
		const channelName = options.getChannelName();
		const channelNumber = options.getChannelNumber();
		const effectiveOptions: RecordingRuleOptions = {
			title: effectiveAiring?.title ?? channelName,
			...ruleOptions,
		};
		const seriesId = effectiveAiring?.series_id || 'auto';
		const targetChannel = effectiveOptions.channel !== undefined ? effectiveOptions.channel : channelNumber;

		try {
			if (options.getIsWatchSession() && options.getWatchSessionId()) {
				await api.promoteWatch(options.getWatchSessionId()!, {
					title: effectiveAiring?.title ?? channelName,
					episode_title: effectiveAiring?.episode_title ?? undefined,
				});
			}

			const onRecordSeries = options.getOnRecordSeries ? options.getOnRecordSeries() : options.onRecordSeries;
			if (onRecordSeries) {
				await onRecordSeries(seriesId, targetChannel, effectiveOptions);
			} else {
				const payload = buildSeriesRulePayload({
					seriesId,
					channel: targetChannel,
					options: effectiveOptions,
				});
				const updatedRules = await api.addHDHomeRunRecordingRule(payload);
				if (Array.isArray(updatedRules)) {
					options.setRecordingRules(updatedRules);
				}
			}
		} catch (err) {
			options.setErrorMessage(getErrorText(err));
		} finally {
			options.setInternalRecordingLoading(false);
		}
	}

	async function handleCancelRecording(): Promise<void> {
		const currentRule = options.getCurrentRule();
		if (!currentRule) return;

		options.setErrorMessage(null);
		options.setShowRecordMenu(false);
		options.setInternalRecordingLoading(true);

		try {
			const onCancelRule = options.getOnCancelRule ? options.getOnCancelRule() : options.onCancelRule;
			if (onCancelRule) {
				await onCancelRule(currentRule.RecordingRuleID);
			} else {
				await api.deleteHDHomeRunRecordingRule(currentRule.RecordingRuleID);
			}
		} catch (err) {
			options.setErrorMessage(getErrorText(err));
		} finally {
			options.setInternalRecordingLoading(false);
		}
	}

	async function handleUpdateRule(
		ruleId: string,
		mode: 'episode' | 'series',
		ruleOptions: RecordingRuleOptions,
	): Promise<void> {
		options.setErrorMessage(null);
		options.setShowRecordMenu(false);
		options.setShowOptionsDialog(false);
		options.setInternalRecordingLoading(true);

		try {
			const onUpdateRule = options.getOnUpdateRule ? options.getOnUpdateRule() : options.onUpdateRule;
			if (onUpdateRule) {
				await onUpdateRule(ruleId, mode, ruleOptions);
			} else {
				const payload = buildUpdateRulePayload(ruleOptions);
				await api.updateHDHomeRunRecordingRule(ruleId, payload);
			}
		} catch (err) {
			options.setErrorMessage(getErrorText(err));
		} finally {
			options.setInternalRecordingLoading(false);
		}
	}

	function handleConfirmOptions(mode: 'episode' | 'series', ruleOptions: RecordingRuleOptions): void {
		const currentRule = options.getCurrentRule();
		if (currentRule) {
			handleUpdateRule(currentRule.RecordingRuleID, mode, ruleOptions);
			return;
		}
		if (mode === 'series') {
			handleRecordSeries(ruleOptions);
		} else {
			handleRecordEpisode(ruleOptions);
		}
	}

	return {
		handleRecordEpisode,
		handleRecordSeries,
		handleCancelRecording,
		handleUpdateRule,
		handleConfirmOptions,
	};
}
