import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const {
	testHDHomeRunTunerConnection,
	testHDHomeRunDvrConnection,
	testHDHomeRunSshConnection,
	testHDHomeRunRecordingsMount,
	updateNetworkIntegration,
} = vi.hoisted(() => ({
	testHDHomeRunTunerConnection: vi.fn(),
	testHDHomeRunDvrConnection: vi.fn(),
	testHDHomeRunSshConnection: vi.fn(),
	testHDHomeRunRecordingsMount: vi.fn(),
	updateNetworkIntegration: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: {
		testHDHomeRunTunerConnection,
		testHDHomeRunDvrConnection,
		testHDHomeRunSshConnection,
		testHDHomeRunRecordingsMount,
		updateNetworkIntegration,
	},
}));

import HDHomeRunNetworkSection from './HDHomeRunNetworkSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	updateNetworkIntegration.mockResolvedValue({ settings: {} });
});

describe('HDHomeRunNetworkSection', () => {
	it('seeds the tuner/DVR inputs from initialSettings', async () => {
		render(HDHomeRunNetworkSection, {
			initialSettings: {
				tuner_host: 'hdhomerun.local',
				tuner_port: 81,
				dvr_host: 'dvr.local',
				dvr_port: 59091,
				dvr_recordings_path: '/mnt/hdhomerun-recordings',
			},
		});

		await waitFor(() => expect(screen.getAllByLabelText('Host')[0]).toHaveValue('hdhomerun.local'));
		expect(screen.getAllByLabelText('Port')[0]).toHaveValue(81);
		expect(screen.getAllByLabelText('Host')[1]).toHaveValue('dvr.local');
		expect(screen.getAllByLabelText('Port')[1]).toHaveValue(59091);
		expect(screen.getByLabelText('Recordings path (local mount)')).toHaveValue('/mnt/hdhomerun-recordings');
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
				dvr_port: 50000,
				dvr_recordings_path: '',
				dvr_ssh_enabled: false,
				dvr_ssh_host: '',
				dvr_ssh_port: 22,
				dvr_ssh_username: '',
			}),
		);
	});

	it('shows an error message when saving fails', async () => {
		updateNetworkIntegration.mockRejectedValue(new Error('boom'));
		render(HDHomeRunNetworkSection, { initialSettings: null });

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		expect(await screen.findByText('Could not save these settings.')).toBeInTheDocument();
	});

	it('reveals SSH fields only once monitoring is enabled, and omits blank secrets from save', async () => {
		render(HDHomeRunNetworkSection, {
			initialSettings: { dvr_ssh_enabled: false, has_dvr_ssh_key: false, has_dvr_ssh_password: false },
		});

		expect(screen.queryByLabelText('Username')).not.toBeInTheDocument();

		await fireEvent.click(screen.getByLabelText(/identify clients/i));
		expect(screen.getByLabelText('Username')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() =>
			expect(updateNetworkIntegration).toHaveBeenCalledWith(
				'hdhomerun',
				expect.not.objectContaining({ dvr_ssh_key: expect.anything(), dvr_ssh_password: expect.anything() }),
			),
		);
	});

	it('tests the SSH connection', async () => {
		testHDHomeRunSshConnection.mockResolvedValue({ ok: true, detail: 'Connected to dvr.local via SSH', error: null });
		render(HDHomeRunNetworkSection, { initialSettings: { dvr_ssh_enabled: true } });

		await fireEvent.click(screen.getAllByRole('button', { name: 'Test connection' })[2]);

		expect(await screen.findByText('✓ Connected to dvr.local via SSH')).toBeInTheDocument();
	});

	it('tests the recordings mount', async () => {
		testHDHomeRunRecordingsMount.mockResolvedValue({
			ok: true,
			detail: 'Mounted and writable; 2 of 2 DVR recordings found.',
			error: null,
		});
		render(HDHomeRunNetworkSection, { initialSettings: { dvr_recordings_path: '/mnt/hdhomerun-recordings' } });

		await fireEvent.click(screen.getByRole('button', { name: 'Test recordings mount' }));

		expect(await screen.findByText('✓ Mounted and writable; 2 of 2 DVR recordings found.')).toBeInTheDocument();
		expect(testHDHomeRunRecordingsMount).toHaveBeenCalledWith(
			expect.objectContaining({ dvr_recordings_path: '/mnt/hdhomerun-recordings' }),
		);
	});

	it('shows the reason when the recordings mount check fails', async () => {
		testHDHomeRunRecordingsMount.mockResolvedValue({
			ok: false,
			detail: null,
			error: '/mnt/x is not writable by the backend process.',
		});
		render(HDHomeRunNetworkSection, { initialSettings: { dvr_recordings_path: '/mnt/x' } });

		await fireEvent.click(screen.getByRole('button', { name: 'Test recordings mount' }));

		expect(await screen.findByText('✗ /mnt/x is not writable by the backend process.')).toBeInTheDocument();
	});
});
