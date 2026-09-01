<script lang="ts">
	import { api, type AdminJob, type JobRun } from '$lib/api';
	import { user } from '$lib/stores/user';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	let jobs = $state<AdminJob[]>([]);
	let jobsError = $state<string | null>(null);
	let jobsLoading = $state(false);
	let triggeringJobId = $state<string | null>(null);

	loadOnceWhen(() => $user?.role === 'admin', loadJobs);

	async function loadJobs() {
		jobsLoading = true;
		jobsError = null;
		try {
			jobs = await api.listJobs();
		} catch {
			jobsError = 'Could not load scheduled tasks.';
		} finally {
			jobsLoading = false;
		}
	}

	async function runJobNow(id: string) {
		triggeringJobId = id;
		jobsError = null;
		try {
			await api.triggerJob(id);
			setTimeout(loadJobs, 1000);
		} catch {
			jobsError = 'Could not trigger the job.';
		} finally {
			triggeringJobId = null;
		}
	}

	function formatDuration(run: JobRun): string {
		if (run.status === 'running' || !run.finished_at) {
			return 'in progress';
		}
		const seconds = (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000;
		return `${seconds.toFixed(1)}s`;
	}
</script>

<section>
	<div class="section-header-row">
		<h3>Scheduled tasks</h3>
		<button class="clear" onclick={loadJobs} disabled={jobsLoading}>
			{jobsLoading ? 'Refreshing…' : 'Refresh'}
		</button>
	</div>

	{#if jobsError}
		<p class="hint error">{jobsError}</p>
	{/if}

	{#if jobsLoading && jobs.length === 0}
		<p class="hint">Loading…</p>
	{:else}
		<ul class="job-list">
			{#each jobs as job (job.id)}
				<li class="job-card">
					<div class="job-header">
						<span class="job-name">{job.name}</span>
						<span class="trigger-badge" class:event={job.trigger === 'event'}>
							{job.trigger === 'interval' ? 'Scheduled' : 'Event-driven'}
						</span>
						{#if job.trigger === 'interval'}
							<button class="clear" onclick={() => runJobNow(job.id)} disabled={triggeringJobId === job.id}>
								{triggeringJobId === job.id ? 'Running…' : 'Run now'}
							</button>
						{/if}
					</div>
					<p class="hint">{job.description}</p>

					{#if job.recent_runs.length === 0}
						<p class="hint">No runs yet.</p>
					{:else}
						<ul class="run-list">
							{#each job.recent_runs as run (run.id)}
								<li class="run-row">
									<span class="job-status {run.status}">{run.status}</span>
									<span class="run-started">{new Date(run.started_at).toLocaleString()}</span>
									<span class="run-duration">{formatDuration(run)}</span>
									{#if run.status === 'failed' && run.error}
										<span class="hint error run-error">{run.error}</span>
									{/if}
								</li>
							{/each}
						</ul>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.job-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.job-card {
		padding: 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
	}

	.job-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.job-name {
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.trigger-badge {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--color-accent);
		border: 1px solid var(--color-accent);
		border-radius: 999px;
		padding: 0.1rem 0.5rem;
	}

	.trigger-badge.event {
		color: var(--color-text-muted);
		border-color: var(--color-border);
	}

	.run-list {
		list-style: none;
		margin: 0.5rem 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.run-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-wrap: wrap;
		font-size: 0.85rem;
	}

	.run-error {
		flex-basis: 100%;
	}

	.job-status {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		border-radius: 999px;
		padding: 0.1rem 0.5rem;
		border: 1px solid var(--color-border);
	}

	.job-status.success {
		color: var(--color-success);
		border-color: var(--color-success);
	}

	.job-status.failed {
		color: var(--color-error);
		border-color: var(--color-error);
	}

	.job-status.running {
		color: var(--color-accent);
		border-color: var(--color-accent);
	}

	.run-started {
		color: var(--color-text-muted);
	}

	.run-duration {
		color: var(--color-text-muted);
	}
</style>
