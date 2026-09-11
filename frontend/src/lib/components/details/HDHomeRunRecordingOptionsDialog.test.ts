import { render, screen, fireEvent, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import HDHomeRunRecordingOptionsDialog from './HDHomeRunRecordingOptionsDialog.svelte';
import type { HDHomeRunGuideEntry, HDHomeRunChannel } from '$lib/api';

const airing: HDHomeRunGuideEntry = {
	series_id: 'SH123',
	title: 'Evening News',
	episode_title: null,
	start: 1_700_000_000,
	end: 1_700_003_600,
};

function renderDialog(overrides: { officialDvrActive?: boolean; canRecordSeries?: boolean; channels?: HDHomeRunChannel[] } = {}) {
	const onConfirm = vi.fn();
	const onClose = vi.fn();
	render(HDHomeRunRecordingOptionsDialog, {
		airing,
		channelName: 'KDFW',
		channelNumber: '4.1',
		channels: [
			{ channel_number: '4.1', name: 'KDFW FOX', is_hd: true, is_drm: false, stream_url: '/stream/4.1', playback_url: '/play/4.1', now: null, next: null },
			{ channel_number: '5.1', name: 'KXAS NBC', is_hd: true, is_drm: false, stream_url: '/stream/5.1', playback_url: '/play/5.1', now: null, next: null },
			{ channel_number: '8.1', name: 'WFAA ABC', is_hd: true, is_drm: false, stream_url: '/stream/8.1', playback_url: '/play/8.1', now: null, next: null },
		],
		canRecordSeries: true,
		officialDvrActive: false,
		loading: false,
		onConfirm,
		onClose,
		...overrides,
	});
	return { onConfirm, onClose };
}

describe('HDHomeRunRecordingOptionsDialog', () => {
	it('confirms with default fields when defaults are left unchanged', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));

		expect(onConfirm).toHaveBeenCalledWith('episode', {
			title: 'Evening News',
			titleMatchMode: 'exact',
			keywordQuery: undefined,
			channel: '4.1',
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: undefined,
			server: undefined,
		});
	});

	it('omits max_episodes_to_keep while retention mode stays "Unlimited"', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.input(screen.getByLabelText('Start early (minutes)'), { target: { value: '5' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Record Series' }));

		expect(onConfirm).toHaveBeenCalledWith('series', {
			title: 'Evening News',
			titleMatchMode: 'exact',
			keywordQuery: undefined,
			channel: '4.1',
			startPadding: 300,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: undefined,
			server: undefined,
		});
	});

	it('sends max_episodes_to_keep when "Keep last N" is selected', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.click(screen.getByLabelText('Keep last 3'));
		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));

		expect(onConfirm).toHaveBeenCalledWith('episode', {
			title: 'Evening News',
			titleMatchMode: 'exact',
			keywordQuery: undefined,
			channel: '4.1',
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: 3,
			server: undefined,
		});
	});

	it('supports selecting "Any channel"', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.click(screen.getByLabelText('Any channel'));
		await fireEvent.click(screen.getByRole('button', { name: 'Record Series' }));

		expect(onConfirm).toHaveBeenCalledWith('series', {
			title: 'Evening News',
			titleMatchMode: 'exact',
			keywordQuery: undefined,
			channel: undefined,
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: undefined,
			server: undefined,
		});
	});

	it('supports selecting multiple specific channels', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.click(screen.getByLabelText('Specific channels'));
		// Check second channel 5.1 in addition to default 4.1
		const ch5Checkbox = screen.getByLabelText(/5.1 KXAS NBC/);
		await fireEvent.click(ch5Checkbox);

		await fireEvent.click(screen.getByRole('button', { name: 'Record Series' }));

		expect(onConfirm).toHaveBeenCalledWith('series', {
			title: 'Evening News',
			titleMatchMode: 'exact',
			keywordQuery: undefined,
			channel: '4.1|5.1',
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: undefined,
			server: undefined,
		});
	});

	it('supports keyword filtering and automatically targets builtin server', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.input(screen.getByPlaceholderText('e.g. Ohio State, Michigan'), {
			target: { value: 'Ohio State, Michigan' },
		});
		await fireEvent.click(screen.getByRole('button', { name: /Record Series \(Keywords\)/ }));

		expect(onConfirm).toHaveBeenCalledWith('series', {
			title: 'Evening News',
			titleMatchMode: 'exact',
			keywordQuery: 'Ohio State, Michigan',
			channel: '4.1',
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: undefined,
			server: 'builtin',
		});
	});

	it('supports title match mode "contains"', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.click(screen.getByLabelText('Contains'));
		await fireEvent.click(screen.getByRole('button', { name: /Record Series \(Keywords\)/ }));

		expect(onConfirm).toHaveBeenCalledWith('series', {
			title: 'Evening News',
			titleMatchMode: 'contains',
			keywordQuery: undefined,
			channel: '4.1',
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: undefined,
			server: 'builtin',
		});
	});

	it('populates keyword from subtitle suggestion chip', async () => {
		const onConfirm = vi.fn();
		render(HDHomeRunRecordingOptionsDialog, {
			airing: {
				series_id: 'SH123',
				title: 'College Football',
				episode_title: 'Ohio State vs Michigan',
				start: 1_700_000_000,
				end: 1_700_003_600,
			},
			channelName: 'FOX',
			channelNumber: '4.1',
			canRecordSeries: true,
			officialDvrActive: false,
			loading: false,
			onConfirm,
			onClose: vi.fn(),
		});

		const chip = screen.getByRole('button', { name: /\+ Use subtitle: "Ohio State vs Michigan"/ });
		expect(chip).toBeInTheDocument();
		await fireEvent.click(chip);

		const keywordInput = screen.getByPlaceholderText('e.g. Ohio State, Michigan') as HTMLInputElement;
		expect(keywordInput.value).toBe('Ohio State vs Michigan');

		await fireEvent.click(screen.getByRole('button', { name: /Record Series \(Keywords\)/ }));
		expect(onConfirm).toHaveBeenCalledWith('series', {
			title: 'College Football',
			titleMatchMode: 'exact',
			keywordQuery: 'Ohio State vs Michigan',
			channel: '4.1',
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: undefined,
			server: 'builtin',
		});
	});

	it('hides the retention control and shows a note when the official DVR is active and no keywords are set', () => {
		renderDialog({ officialDvrActive: true });

		expect(
			screen.getByText('Managed by your HDHomeRun DVR subscription — episode retention isn\'t configurable here.'),
		).toBeInTheDocument();
		expect(screen.queryByText('Unlimited')).not.toBeInTheDocument();
		expect(screen.queryByLabelText(/Keep last/)).not.toBeInTheDocument();
	});

	it('displays deduplication note and documentation link when official DVR is active', () => {
		renderDialog({ officialDvrActive: true });

		expect(
			screen.getByText(/HDHomeRun DVR tracks unique episodes in the cloud and skips repeats/i),
		).toBeInTheDocument();
		const docLink = screen.getByRole('link', { name: /How HDHomeRun deduplication works/i });
		expect(docLink).toBeInTheDocument();
		expect(docLink).toHaveAttribute('href', 'https://info.hdhomerun.com/info/dvr:instructions');
	});

	it('does not render a "Record Series" button when canRecordSeries is false', () => {
		renderDialog({ canRecordSeries: false });

		expect(screen.queryByRole('button', { name: 'Record Series' })).not.toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Record Episode/ })).toBeInTheDocument();
	});

	it('calls onClose when the close button is clicked', async () => {
		const { onClose } = renderDialog();

		await fireEvent.click(screen.getByRole('button', { name: 'Close' }));

		expect(onClose).toHaveBeenCalled();
	});

	it('allows selecting a specific recording server', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.change(screen.getByLabelText('Recording Server'), { target: { value: 'builtin' } });
		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));

		expect(onConfirm).toHaveBeenCalledWith('episode', {
			title: 'Evening News',
			titleMatchMode: 'exact',
			keywordQuery: undefined,
			channel: '4.1',
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: undefined,
			server: 'builtin',
		});
	});

	it('renders rich show details, badges, synopsis, and episode info', () => {
		const richAiring: HDHomeRunGuideEntry = {
			series_id: 'SH999',
			title: 'Science Mystery',
			episode_title: 'The Hidden Quantum Realm',
			season_number: 2,
			episode_number: '5',
			synopsis: 'A deep dive into quantum particles and strange phenomena.',
			start: 1_700_000_000,
			end: 1_700_003_600,
			original_airdate: '2023-11-14',
			image_url: 'https://example.com/poster.jpg',
			category: 'Science, Documentary',
			is_new: true,
			has_cc: true,
			is_hd: true,
			audio: 'stereo',
		};

		render(HDHomeRunRecordingOptionsDialog, {
			airing: richAiring,
			channelName: 'Discovery',
			channelNumber: '10.1',
			isHd: true,
			canRecordSeries: true,
			officialDvrActive: false,
			loading: false,
			onConfirm: vi.fn(),
			onClose: vi.fn(),
		});

		expect(screen.getByText('Science Mystery')).toBeInTheDocument();
		expect(screen.getByText('S2E5 • The Hidden Quantum Realm')).toBeInTheDocument();
		expect(screen.getByText('A deep dive into quantum particles and strange phenomena.')).toBeInTheDocument();
		expect(screen.getByText('10.1')).toBeInTheDocument();
		expect(screen.getByText('Discovery')).toBeInTheDocument();
		expect(screen.getAllByText('HD').length).toBeGreaterThan(0);
		expect(screen.getByText('CC')).toBeInTheDocument();
		expect(screen.getByText('STEREO')).toBeInTheDocument();
		expect(screen.getByText('NEW')).toBeInTheDocument();
		expect(screen.getByText('Science')).toBeInTheDocument();
		expect(screen.getByText('Documentary')).toBeInTheDocument();
		expect(screen.getByText(/Original air date: Nov 14, 2023/)).toBeInTheDocument();
	});

	it('renders update and cancel recording buttons and pre-populates fields when existingRule is present', async () => {
		const onCancelRule = vi.fn();
		const onUpdateRule = vi.fn();
		const onClose = vi.fn();
		render(HDHomeRunRecordingOptionsDialog, {
			airing,
			channelName: 'KDFW',
			channelNumber: '4.1',
			channels: [
				{ channel_number: '4.1', name: 'KDFW FOX', is_hd: true, is_drm: false, stream_url: '/stream/4.1', playback_url: '/play/4.1', now: null, next: null },
				{ channel_number: '5.1', name: 'KXAS NBC', is_hd: true, is_drm: false, stream_url: '/stream/5.1', playback_url: '/play/5.1', now: null, next: null },
			],
			canRecordSeries: true,
			officialDvrActive: false,
			loading: false,
			existingRule: {
				RecordingRuleID: 'rule_123',
				SeriesID: 'SH123',
				Title: 'Evening News',
				StartPadding: 300,
				EndPadding: 600,
				RecentOnly: 1,
				MaxEpisodesToKeep: 5,
				TitleMatchMode: 'contains',
				KeywordQuery: 'special report',
				ChannelOnly: '5.1',
				provider: 'builtin',
			},
			onCancelRule,
			onConfirm: vi.fn(),
			onUpdateRule,
			onClose,
		});

		const startPaddingInput = screen.getByLabelText('Start early (minutes)') as HTMLInputElement;
		expect(startPaddingInput.value).toBe('5');

		const endPaddingInput = screen.getByLabelText('End late (minutes)') as HTMLInputElement;
		expect(endPaddingInput.value).toBe('10');

		const newEpisodesOnlyCheckbox = screen.getByLabelText('New episodes only') as HTMLInputElement;
		expect(newEpisodesOnlyCheckbox.checked).toBe(true);

		const keywordInput = screen.getByPlaceholderText('e.g. Ohio State, Michigan') as HTMLInputElement;
		expect(keywordInput.value).toBe('special report');

		const updateBtn = screen.getByRole('button', { name: 'Update Recording' });
		expect(updateBtn).toBeInTheDocument();

		const cancelBtn = screen.getByRole('button', { name: 'Cancel Recording' });
		expect(cancelBtn).toBeInTheDocument();

		const closeBtns = screen.getAllByRole('button', { name: 'Close' });
		expect(closeBtns.length).toBeGreaterThanOrEqual(1);

		await fireEvent.click(updateBtn);
		expect(onUpdateRule).toHaveBeenCalledWith('rule_123', 'series', {
			title: 'Evening News',
			titleMatchMode: 'contains',
			keywordQuery: 'special report',
			channel: '5.1',
			startPadding: 300,
			endPadding: 600,
			recentOnly: true,
			maxEpisodesToKeep: 5,
			server: 'builtin',
		});

		await fireEvent.click(cancelBtn);
		const cancelModal = await screen.findByRole('alertdialog');
		expect(cancelModal).toBeInTheDocument();
		const modalConfirmBtn = within(cancelModal).getByRole('button', { name: 'Cancel Recording' });
		// A real browser fires pointerdown before click; the confirm button lives
		// outside the dialog's own root element, so a naive "click outside closes
		// the dialog" listener bound to window pointerdown would tear the dialog
		// (and this button) down before the click ever reaches onCancelRule.
		await fireEvent.pointerDown(modalConfirmBtn);
		await fireEvent.click(modalConfirmBtn);

		expect(onCancelRule).toHaveBeenCalledWith('rule_123');
		expect(onClose).toHaveBeenCalled();
	});

	it('defaults server to builtin when airing lacks series_id', async () => {
		const airingWithoutSeriesId: HDHomeRunGuideEntry = {
			series_id: undefined,
			title: 'Local News Broadcast',
			episode_title: null,
			start: 1_700_000_000,
			end: 1_700_003_600,
		};
		const onConfirm = vi.fn();
		render(HDHomeRunRecordingOptionsDialog, {
			airing: airingWithoutSeriesId,
			channelName: 'KDFW',
			channelNumber: '4.1',
			channels: [{ channel_number: '4.1', name: 'KDFW FOX', is_hd: true, is_drm: false, stream_url: '', playback_url: null, now: null, next: null }],
			canRecordSeries: true,
			officialDvrActive: true,
			loading: false,
			onConfirm,
			onClose: vi.fn(),
		});

		const serverSelect = screen.getByLabelText('Recording Server') as HTMLSelectElement;
		expect(serverSelect.value).toBe('builtin');

		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));
		const fallbackModal = await screen.findByRole('alertdialog');
		expect(fallbackModal).toBeInTheDocument();
		expect(within(fallbackModal).getByText(/Schedule on Built-in DVR\?/i)).toBeInTheDocument();

		const fallbackConfirmBtn = within(fallbackModal).getByRole('button', { name: 'Schedule on Built-in DVR' });
		// Same outside-click hazard as the cancel-rule confirm modal: this button
		// lives outside the parent dialog's root element.
		await fireEvent.pointerDown(fallbackConfirmBtn);
		await fireEvent.click(fallbackConfirmBtn);
		expect(onConfirm).toHaveBeenCalledWith('episode', expect.objectContaining({
			server: 'builtin',
		}));
	});

	it('shows fallback hint when airing lacks series_id and user selects hdhomerun', async () => {
		const airingWithoutSeriesId: HDHomeRunGuideEntry = {
			series_id: undefined,
			title: 'Local News Broadcast',
			episode_title: null,
			start: 1_700_000_000,
			end: 1_700_003_600,
		};
		render(HDHomeRunRecordingOptionsDialog, {
			airing: airingWithoutSeriesId,
			channelName: 'KDFW',
			channelNumber: '4.1',
			channels: [{ channel_number: '4.1', name: 'KDFW FOX', is_hd: true, is_drm: false, stream_url: '', playback_url: null, now: null, next: null }],
			canRecordSeries: true,
			officialDvrActive: false,
			loading: false,
			onConfirm: vi.fn(),
			onClose: vi.fn(),
		});

		const serverSelect = screen.getByLabelText('Recording Server');
		await fireEvent.change(serverSelect, { target: { value: 'hdhomerun' } });

		expect(screen.getByText(/HDHomeRun DVR requires a SiliconDust Series ID/i)).toBeInTheDocument();
	});

	it('shows fallback notice when existing rule has fallback_reason', () => {
		render(HDHomeRunRecordingOptionsDialog, {
			airing,
			channelName: 'KDFW',
			channelNumber: '4.1',
			channels: [{ channel_number: '4.1', name: 'KDFW FOX', is_hd: true, is_drm: false, stream_url: '', playback_url: null, now: null, next: null }],
			canRecordSeries: true,
			officialDvrActive: false,
			loading: false,
			existingRule: {
				RecordingRuleID: 'rule_fb',
				SeriesID: 'SH_FB',
				Title: 'Evening News',
				fallback_reason: 'Airing lacks a SiliconDust Series ID in the guide; fell back to Built-in DVR.',
				provider: 'builtin',
			},
			onConfirm: vi.fn(),
			onClose: vi.fn(),
		});

		expect(screen.getByText(/Scheduled on Built-in DVR: "Evening News" lacks a SiliconDust Series ID/i)).toBeInTheDocument();
	});

	it('cancelling fallback modal aborts scheduling', async () => {
		const airingWithoutSeriesId: HDHomeRunGuideEntry = {
			series_id: undefined,
			title: 'Far Future Program',
			episode_title: null,
			start: 1_700_000_000,
			end: 1_700_003_600,
		};
		const onConfirm = vi.fn();
		render(HDHomeRunRecordingOptionsDialog, {
			airing: airingWithoutSeriesId,
			channelName: 'KDFW',
			channelNumber: '4.1',
			channels: [{ channel_number: '4.1', name: 'KDFW FOX', is_hd: true, is_drm: false, stream_url: '', playback_url: null, now: null, next: null }],
			canRecordSeries: true,
			officialDvrActive: true,
			loading: false,
			onConfirm,
			onClose: vi.fn(),
		});

		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));
		const modal = await screen.findByRole('alertdialog');
		await fireEvent.click(within(modal).getByRole('button', { name: 'Cancel' }));

		expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
		expect(onConfirm).not.toHaveBeenCalled();
	});

	it('clicking Keep Recording in cancel modal dismisses without deleting rule', async () => {
		const onCancelRule = vi.fn();
		const onClose = vi.fn();
		render(HDHomeRunRecordingOptionsDialog, {
			airing,
			channelName: 'KDFW',
			channelNumber: '4.1',
			channels: [{ channel_number: '4.1', name: 'KDFW FOX', is_hd: true, is_drm: false, stream_url: '', playback_url: null, now: null, next: null }],
			canRecordSeries: true,
			officialDvrActive: false,
			loading: false,
			existingRule: {
				RecordingRuleID: 'rule_123',
				SeriesID: 'SH123',
				Title: 'Evening News',
				provider: 'builtin',
			},
			onCancelRule,
			onConfirm: vi.fn(),
			onClose,
		});

		await fireEvent.click(screen.getByRole('button', { name: 'Cancel Recording' }));
		const modal = await screen.findByRole('alertdialog');
		await fireEvent.click(within(modal).getByRole('button', { name: 'Keep Recording' }));

		expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
		expect(onCancelRule).not.toHaveBeenCalled();
		expect(onClose).not.toHaveBeenCalled();
	});

	it('checking Don\'t ask again suppresses fallback confirmation', async () => {
		localStorage.clear();
		const airingWithoutSeriesId: HDHomeRunGuideEntry = {
			series_id: undefined,
			title: 'Far Future Program',
			episode_title: null,
			start: 1_700_000_000,
			end: 1_700_003_600,
		};
		const onConfirm = vi.fn();
		const { unmount } = render(HDHomeRunRecordingOptionsDialog, {
			airing: airingWithoutSeriesId,
			channelName: 'KDFW',
			channelNumber: '4.1',
			channels: [{ channel_number: '4.1', name: 'KDFW FOX', is_hd: true, is_drm: false, stream_url: '', playback_url: null, now: null, next: null }],
			canRecordSeries: true,
			officialDvrActive: true,
			loading: false,
			onConfirm,
			onClose: vi.fn(),
		});

		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));
		const modal = await screen.findByRole('alertdialog');

		// Check "Don't ask again"
		const checkbox = within(modal).getByRole('checkbox');
		await fireEvent.click(checkbox);
		await fireEvent.click(within(modal).getByRole('button', { name: 'Schedule on Built-in DVR' }));

		expect(onConfirm).toHaveBeenCalledTimes(1);
		expect(localStorage.getItem('hdhomerun_suppress_fallback_confirm')).toBe('true');
		unmount();

		// Next time, it should directly call onConfirm without opening the modal
		const onConfirm2 = vi.fn();
		render(HDHomeRunRecordingOptionsDialog, {
			airing: airingWithoutSeriesId,
			channelName: 'KDFW',
			channelNumber: '4.1',
			channels: [{ channel_number: '4.1', name: 'KDFW FOX', is_hd: true, is_drm: false, stream_url: '', playback_url: null, now: null, next: null }],
			canRecordSeries: true,
			officialDvrActive: true,
			loading: false,
			onConfirm: onConfirm2,
			onClose: vi.fn(),
		});

		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));
		expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
		expect(onConfirm2).toHaveBeenCalledTimes(1);
		localStorage.clear();
	});
});

