import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { testHDHomeRunTunerConnection, testHDHomeRunDvrConnection, updateNetworkIntegration } = vi.hoisted(() => ({
	testHDHomeRunTunerConnection: vi.fn(),
	testHDHomeRunDvrConnection: vi.fn(),
	updateNetworkIntegration: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { testHDHomeRunTunerConnection, testHDHomeRunDvrConnection, updateNetworkIntegration },
}));

import HDHomeRunNetworkSection from './HDHomeRunNetworkSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	updateNetworkIntegration.mockResolvedValue({ settings: {} });
});

describe('HDHomeRunNetworkSection', () => {
	it('seeds the tuner/DVR inputs from initialSettings', async () => {
		render(HDHomeRunNetworkSection, {
			initialSettings: { tuner_host: 'hdhomerun.local', tuner_port: 81, dvr_host: 'dvr.local', dvr_port: 59091 },
		});

		await waitFor(() => expect(screen.getAllByLabelText('Host')[0]).toHaveValue('hdhomerun.local'));
		expect(screen.getAllByLabelText('Port')[0]).toHaveValue(81);
		expect(screen.getAllByLabelText('Host')[1]).toHaveValue('dvr.local');
		expect(screen.getAllByLabelText('Port')[1]).toHaveValue(59091);
	});

	it('tests the tuner connection', async () => {
		testHDHomeRunTunerConnection.mockResolvedValue({ ok: true, detail: 'v1.2.3', error: null });
		render(HDHomeRunNetworkSection, { initialSettings: null });

		await fireEvent.click(screen.getAllByRole('button', { name: 'Test connection' })[0]);

		expect(await screen.findByText('✓ v1.2.3')).toBeInTheDocument();
	});

	it('saves the tuner/DVR settings', async () => {
		render(HDHomeRunNetworkSection, { initialSettings: null });

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() =>
			expect(updateNetworkIntegration).toHaveBeenCalledWith('hdhomerun', {
				tuner_host: '',
				tuner_port: 80,
				dvr_host: '',
				dvr_port: 59090,
			}),
		);
	});

	it('shows an error message when saving fails', async () => {
		updateNetworkIntegration.mockRejectedValue(new Error('boom'));
		render(HDHomeRunNetworkSection, { initialSettings: null });

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		expect(await screen.findByText('Could not save these settings.')).toBeInTheDocument();
	});
});
