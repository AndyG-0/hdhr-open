import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import HDHomeRunRecordingOptionsDialog from './HDHomeRunRecordingOptionsDialog.svelte';
import type { HDHomeRunGuideEntry } from '$lib/api';

const airing: HDHomeRunGuideEntry = {
	series_id: 'SH123',
	title: 'Evening News',
	episode_title: null,
	start: 1_700_000_000,
	end: 1_700_003_600,
};

function renderDialog(overrides: { officialDvrActive?: boolean; canRecordSeries?: boolean } = {}) {
	const onConfirm = vi.fn();
	const onClose = vi.fn();
	render(HDHomeRunRecordingOptionsDialog, {
		airing,
		channelName: 'KDFW',
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
	it('confirms with no extra fields when defaults are left unchanged', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));

		expect(onConfirm).toHaveBeenCalledWith('episode', {
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: undefined,
			maxEpisodesToKeep: undefined,
		});
	});

	it('omits max_episodes_to_keep while retention mode stays "Unlimited"', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.input(screen.getByLabelText('Start early (minutes)'), { target: { value: '5' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Record Series' }));

		expect(onConfirm).toHaveBeenCalledWith('series', {
			startPadding: 300,
			endPadding: undefined,
			recentOnly: undefined,
			maxEpisodesToKeep: undefined,
		});
	});

	it('sends max_episodes_to_keep when "Keep last N" is selected', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.click(screen.getByLabelText('Keep last 3'));
		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));

		expect(onConfirm).toHaveBeenCalledWith('episode', {
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: undefined,
			maxEpisodesToKeep: 3,
		});
	});

	it('hides the retention control and shows a note when the official DVR is active', () => {
		renderDialog({ officialDvrActive: true });

		expect(
			screen.getByText('Managed by your HDHomeRun DVR subscription — episode retention isn\'t configurable here.'),
		).toBeInTheDocument();
		expect(screen.queryByText('Unlimited')).not.toBeInTheDocument();
		expect(screen.queryByLabelText(/Keep last/)).not.toBeInTheDocument();
	});

	it('does not render a "Record Series" button when the airing has no series', () => {
		renderDialog({ canRecordSeries: false });

		expect(screen.queryByRole('button', { name: 'Record Series' })).not.toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Record Episode/ })).toBeInTheDocument();
	});

	it('calls onClose when the close button is clicked', async () => {
		const { onClose } = renderDialog();

		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

		expect(onClose).toHaveBeenCalled();
	});

	it('allows selecting a specific recording server', async () => {
		const { onConfirm } = renderDialog();

		await fireEvent.change(screen.getByLabelText('Recording Server'), { target: { value: 'builtin' } });
		await fireEvent.click(screen.getByRole('button', { name: /Record Episode/ }));

		expect(onConfirm).toHaveBeenCalledWith('episode', {
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: undefined,
			maxEpisodesToKeep: undefined,
			server: 'builtin',
		});
	});
});
