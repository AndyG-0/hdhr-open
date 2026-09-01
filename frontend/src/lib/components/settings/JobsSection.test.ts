import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { listJobs, triggerJob } = vi.hoisted(() => ({
	listJobs: vi.fn(),
	triggerJob: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { listJobs, triggerJob },
}));

import { user } from '$lib/stores/user';
import JobsSection from './JobsSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	user.set({ id: 'u1', name: 'Admin', avatar: null, role: 'admin' });
});

describe('JobsSection', () => {
	it('loads and renders jobs with their trigger type and run history', async () => {
		listJobs.mockResolvedValue([
			{
				id: 'hls_reap',
				name: 'HLS session reap',
				description: 'Reaps idle HLS sessions.',
				trigger: 'interval',
				recent_runs: [
					{
						id: 'r1',
						job_id: 'hls_reap',
						status: 'success',
						started_at: '2026-08-31T00:00:00Z',
						finished_at: '2026-08-31T00:00:02Z',
						error: null,
					},
				],
			},
			{
				id: 'caption_extract',
				name: 'Caption extraction',
				description: 'Extracts captions on recording completion.',
				trigger: 'event',
				recent_runs: [],
			},
		]);
		render(JobsSection);

		expect(await screen.findByText('HLS session reap')).toBeInTheDocument();
		expect(screen.getByText('Scheduled')).toBeInTheDocument();
		expect(screen.getByText('Event-driven')).toBeInTheDocument();
		expect(screen.getByText('success')).toBeInTheDocument();
		expect(screen.getByText('2.0s')).toBeInTheDocument();
	});

	it('shows "No runs yet." for a job with no history, and only renders "Run now" for interval jobs', async () => {
		listJobs.mockResolvedValue([
			{
				id: 'hls_reap',
				name: 'HLS session reap',
				description: 'Reaps idle HLS sessions.',
				trigger: 'interval',
				recent_runs: [],
			},
			{
				id: 'caption_extract',
				name: 'Caption extraction',
				description: 'Extracts captions on recording completion.',
				trigger: 'event',
				recent_runs: [],
			},
		]);
		render(JobsSection);

		await screen.findByText('HLS session reap');
		expect(screen.getAllByText('No runs yet.')).toHaveLength(2);
		expect(screen.getAllByRole('button', { name: 'Run now' })).toHaveLength(1);
	});

	it('shows the error text for a failed run', async () => {
		listJobs.mockResolvedValue([
			{
				id: 'hls_reap',
				name: 'HLS session reap',
				description: 'Reaps idle HLS sessions.',
				trigger: 'interval',
				recent_runs: [
					{
						id: 'r1',
						job_id: 'hls_reap',
						status: 'failed',
						started_at: '2026-08-31T00:00:00Z',
						finished_at: '2026-08-31T00:00:01Z',
						error: 'boom',
					},
				],
			},
		]);
		render(JobsSection);

		expect(await screen.findByText('failed')).toBeInTheDocument();
		expect(screen.getByText('boom')).toBeInTheDocument();
	});

	it('triggers a job run and reloads afterward', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		const job = {
			id: 'hls_reap',
			name: 'HLS session reap',
			description: 'Reaps idle HLS sessions.',
			trigger: 'interval' as const,
			recent_runs: [],
		};
		listJobs.mockResolvedValue([job]);
		triggerJob.mockResolvedValue({ status: 'triggered' });
		render(JobsSection);

		await screen.findByText('HLS session reap');
		const runButton = screen.getByRole('button', { name: 'Run now' });
		await fireEvent.click(runButton);

		await waitFor(() => expect(triggerJob).toHaveBeenCalledWith('hls_reap'));
		expect(listJobs).toHaveBeenCalledTimes(1);

		await vi.advanceTimersByTimeAsync(1000);
		expect(listJobs).toHaveBeenCalledTimes(2);
		vi.useRealTimers();
	});

	it('shows an error message when loading fails', async () => {
		listJobs.mockRejectedValue(new Error('boom'));
		render(JobsSection);

		expect(await screen.findByText('Could not load scheduled tasks.')).toBeInTheDocument();
	});

	it('shows an error message when triggering a job fails', async () => {
		listJobs.mockResolvedValue([
			{
				id: 'hls_reap',
				name: 'HLS session reap',
				description: 'Reaps idle HLS sessions.',
				trigger: 'interval',
				recent_runs: [],
			},
		]);
		triggerJob.mockRejectedValue(new Error('boom'));
		render(JobsSection);

		await screen.findByText('HLS session reap');
		const runButton = screen.getByRole('button', { name: 'Run now' });
		await fireEvent.click(runButton);

		expect(await screen.findByText('Could not trigger the job.')).toBeInTheDocument();
		expect(runButton).not.toBeDisabled();
	});
});
