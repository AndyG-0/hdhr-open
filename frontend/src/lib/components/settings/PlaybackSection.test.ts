import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { hdhomerunTranscodePresets, updateNetworkIntegration, hdhomerunHwaccelDiagnostics } = vi.hoisted(() => ({
	hdhomerunTranscodePresets: vi.fn(),
	updateNetworkIntegration: vi.fn(),
	hdhomerunHwaccelDiagnostics: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { hdhomerunTranscodePresets, updateNetworkIntegration, hdhomerunHwaccelDiagnostics },
}));

import PlaybackSection from './PlaybackSection.svelte';

const presets = [
	{ id: 'software', label: 'Software', description: 'CPU only', input_args: [], output_args: ['-c:v', 'libx264'] },
	{ id: 'custom', label: 'Custom', description: 'Your own args', input_args: [], output_args: [] },
];

beforeEach(() => {
	vi.clearAllMocks();
	hdhomerunTranscodePresets.mockResolvedValue(presets);
	updateNetworkIntegration.mockResolvedValue({ settings: {} });
});

describe('PlaybackSection', () => {
	it('seeds inputs from initialSettings and loads transcode presets', async () => {
		render(PlaybackSection, {
			initialSettings: { playback_mode: 'server_transcode', hwaccel: 'software', ffmpeg_debug: true },
		});

		expect(await screen.findByText('Software')).toBeInTheDocument();
		await waitFor(() => expect(screen.getByLabelText('Verbose ffmpeg logging')).toBeChecked());
	});

	it('shows the external-only hint when mode is external', async () => {
		render(PlaybackSection, { initialSettings: null });

		await fireEvent.click(screen.getByRole('button', { name: 'External player only' }));

		expect(
			screen.getByText('No in-app player — channels only offer a raw stream link to open in an external player like VLC.'),
		).toBeInTheDocument();
	});

	it('saves the playback settings', async () => {
		render(PlaybackSection, { initialSettings: null });
		await screen.findByText('Software');

		await fireEvent.click(screen.getByRole('button', { name: 'Save playback settings' }));

		await waitFor(() =>
			expect(updateNetworkIntegration).toHaveBeenCalledWith('hdhomerun', {
				playback_mode: 'server_transcode',
				hwaccel: 'software',
				custom_ffmpeg_args: '',
				hwaccel_device: '/dev/dri/renderD128',
				ffmpeg_debug: false,
				thumbnails_enabled: true,
			}),
		);
		expect(await screen.findByText('Saved.')).toBeInTheDocument();
	});

	it('runs diagnostics and shows the result', async () => {
		hdhomerunHwaccelDiagnostics.mockResolvedValue({
			summary: ['All good'],
			dri: { dir_exists: false, devices: [] },
			process: { uid: 1000, gid: 1000, groups: [] },
			vainfo: null,
			sample_error: null,
			probes: {},
		});
		render(PlaybackSection, { initialSettings: null });
		await screen.findByText('Software');

		await fireEvent.click(screen.getByRole('button', { name: 'Run diagnostics' }));

		expect(await screen.findByText('All good')).toBeInTheDocument();
	});
});
