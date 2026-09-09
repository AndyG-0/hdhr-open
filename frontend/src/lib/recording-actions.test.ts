import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE_URL: 'http://api.test' } }));

const { promoteWatch, addHDHomeRunRecordingRule, deleteHDHomeRunRecordingRule, updateHDHomeRunRecordingRule } =
	vi.hoisted(() => ({
		promoteWatch: vi.fn().mockResolvedValue({}),
		addHDHomeRunRecordingRule: vi.fn().mockResolvedValue([]),
		deleteHDHomeRunRecordingRule: vi.fn().mockResolvedValue([]),
		updateHDHomeRunRecordingRule: vi.fn().mockResolvedValue([]),
	}));

vi.mock('$lib/api', () => ({
	api: {
		promoteWatch,
		addHDHomeRunRecordingRule,
		deleteHDHomeRunRecordingRule,
		updateHDHomeRunRecordingRule,
	},
}));

import { createRecordingActionsController, type RecordingActionsControllerOptions } from './recording-actions';

describe('recording-actions controller', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	function makeOptions(overrides: Partial<RecordingActionsControllerOptions> = {}): RecordingActionsControllerOptions {
		return {
			getEffectiveAiring: () => ({ title: 'Test Show', series_id: 's1', start: 1000, end: 2000, episode_title: null }),
			getChannelName: () => 'NBC',
			getChannelNumber: () => '4.1',
			getIsWatchSession: () => false,
			getWatchSessionId: () => null,
			getCurrentRule: () => null,
			getRecordingRules: () => [],
			setRecordingRules: vi.fn(),
			setErrorMessage: vi.fn(),
			setInternalRecordingLoading: vi.fn(),
			setShowRecordMenu: vi.fn(),
			setShowOptionsDialog: vi.fn(),
			translate: (key) => key,
			...overrides,
		};
	}

	it('clears error message at the start of handleRecordEpisode', async () => {
		const options = makeOptions();
		const controller = createRecordingActionsController(options);

		await controller.handleRecordEpisode();

		expect(options.setErrorMessage).toHaveBeenNthCalledWith(1, null);
		expect(addHDHomeRunRecordingRule).toHaveBeenCalledWith(
			expect.objectContaining({ series_id: 's1', channel: '4.1', title: 'Test Show' }),
		);
	});

	it('clears error message at the start of handleRecordSeries', async () => {
		const options = makeOptions();
		const controller = createRecordingActionsController(options);

		await controller.handleRecordSeries();

		expect(options.setErrorMessage).toHaveBeenNthCalledWith(1, null);
		expect(addHDHomeRunRecordingRule).toHaveBeenCalledWith(
			expect.objectContaining({ series_id: 's1', channel: '4.1', title: 'Test Show' }),
		);
	});

	it('clears error message at the start of handleCancelRecording', async () => {
		const options = makeOptions({
			getCurrentRule: () => ({ RecordingRuleID: 'rule-123', SeriesID: 's1', Title: 'Show' }),
		});
		const controller = createRecordingActionsController(options);

		await controller.handleCancelRecording();

		expect(options.setErrorMessage).toHaveBeenNthCalledWith(1, null);
		expect(deleteHDHomeRunRecordingRule).toHaveBeenCalledWith('rule-123');
	});

	it('clears error message at the start of handleUpdateRule', async () => {
		const options = makeOptions();
		const controller = createRecordingActionsController(options);

		await controller.handleUpdateRule('rule-123', 'episode', { title: 'Updated Title' });

		expect(options.setErrorMessage).toHaveBeenNthCalledWith(1, null);
		expect(updateHDHomeRunRecordingRule).toHaveBeenCalledWith(
			'rule-123',
			expect.objectContaining({ title: 'Updated Title' }),
		);
	});

	it('surfaces error message when api call fails', async () => {
		addHDHomeRunRecordingRule.mockRejectedValueOnce(new Error('Backend rejected rule'));
		const options = makeOptions();
		const controller = createRecordingActionsController(options);

		await controller.handleRecordEpisode();

		expect(options.setErrorMessage).toHaveBeenLastCalledWith('Backend rejected rule');
	});

	it('promotes watch session instead of adding rule when in watch session', async () => {
		const options = makeOptions({
			getIsWatchSession: () => true,
			getWatchSessionId: () => 'sess-999',
		});
		const controller = createRecordingActionsController(options);

		await controller.handleRecordEpisode();

		expect(promoteWatch).toHaveBeenCalledWith('sess-999', {
			title: 'Test Show',
			episode_title: undefined,
		});
		expect(addHDHomeRunRecordingRule).not.toHaveBeenCalled();
	});

	it('handleConfirmOptions routes to handleUpdateRule when currentRule exists', () => {
		const options = makeOptions({
			getCurrentRule: () => ({ RecordingRuleID: 'rule-exists', SeriesID: 's1', Title: 'Show' }),
		});
		const controller = createRecordingActionsController(options);
		controller.handleConfirmOptions('series', { title: 'New Series Title' });

		expect(updateHDHomeRunRecordingRule).toHaveBeenCalledWith('rule-exists', expect.anything());
	});
});
