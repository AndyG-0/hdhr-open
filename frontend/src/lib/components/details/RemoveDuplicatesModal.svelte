<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { HDHomeRunRecording, HDHomeRunRecordingDuplicateGroup } from '$lib/api';
	import { groupsWithAllSelected, initialSelection, selectionSummary } from '$lib/recording-duplicates';

	interface Props {
		groups: HDHomeRunRecordingDuplicateGroup[];
		loading?: boolean;
		deleting?: boolean;
		onConfirm: (recordingIds: string[]) => void;
		onClose: () => void;
	}

	let { groups, loading = false, deleting = false, onConfirm, onClose }: Props = $props();

	// Resets whenever a fresh set of groups arrives; toggling reassigns it.
	let selected = $derived(initialSelection(groups));

	const fullyChecked = $derived(groupsWithAllSelected(groups, selected));
	const summary = $derived(selectionSummary(groups, selected));

	function toggle(id: string, checked: boolean) {
		const next = new Set(selected);
		if (checked) next.add(id);
		else next.delete(id);
		selected = next;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && !deleting) onClose();
	}

	function formatBytes(bytes: number | null | undefined): string {
		if (bytes == null) return '';
		return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
	}

	function formatDate(seconds: number | null | undefined): string {
		if (seconds == null) return '';
		return new Date(seconds * 1000).toLocaleString([], {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		});
	}

	function formatDuration(seconds: number | null | undefined): string {
		if (seconds == null) return '';
		return $_('hdhomerun.detail.duration_minutes', { values: { minutes: Math.round(seconds / 60) } });
	}

	function episodeLabel(rec: HDHomeRunRecording): string {
		if (rec.season_number != null && rec.episode_number) {
			const ep = rec.episode_number.includes('.') ? rec.episode_number.split('.').pop() : rec.episode_number;
			return `S${rec.season_number}E${ep}`;
		}
		return rec.episode_number ?? '';
	}

	function groupDetails(group: HDHomeRunRecordingDuplicateGroup): string {
		const first = group.recordings[0];
		return [
			group.episode_title,
			first ? episodeLabel(first) : '',
			first?.original_air_date
				? $_('hdhomerun.detail.original_air_date', { values: { date: first.original_air_date } })
				: '',
		]
			.filter(Boolean)
			.join(' · ');
	}

	function recordingMeta(rec: HDHomeRunRecording): string {
		const resolution = rec.video_height ? `${rec.video_height}p` : '';
		const channel = [rec.channel_number, rec.channel_name].filter(Boolean).join(' ');
		return [channel, formatDuration(rec.duration_seconds), formatBytes(rec.file_size_bytes), resolution]
			.filter(Boolean)
			.join(' · ');
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="confirm-backdrop" onclick={() => !deleting && onClose()} role="presentation"></div>
<div class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="remove-duplicates-title">
	<h3 id="remove-duplicates-title" class="confirm-title">{$_('hdhomerun.detail.remove_duplicates_title')}</h3>

	<div class="dialog-body">
		{#if loading}
			<p class="confirm-message">{$_('hdhomerun.detail.remove_duplicates_loading')}</p>
		{:else if groups.length === 0}
			<p class="confirm-message">{$_('hdhomerun.detail.remove_duplicates_none')}</p>
		{:else}
			<p class="confirm-message">{$_('hdhomerun.detail.remove_duplicates_intro')}</p>
			{#each groups as group (group.key)}
				<section class="dup-group" data-testid="duplicate-group">
					<header class="dup-group-header">
						<span class="dup-group-title">{group.title}</span>
						{#if groupDetails(group)}
							<span class="dup-group-details">{groupDetails(group)}</span>
						{/if}
					</header>
					{#if fullyChecked.has(group.key)}
						<p class="dup-warning" role="alert">{$_('hdhomerun.detail.remove_duplicates_all_checked_warning')}</p>
					{/if}
					<ul class="dup-list">
						{#each group.recordings as rec (rec.recording_id)}
							{@const id = rec.recording_id ?? ''}
							<li class="dup-row" class:checked={selected.has(id)}>
								<label>
									<input
										type="checkbox"
										checked={selected.has(id)}
										disabled={deleting}
										aria-label={$_('hdhomerun.detail.remove_duplicates_select_label', {
											values: { title: group.title, date: formatDate(rec.start) },
										})}
										onchange={(e) => toggle(id, e.currentTarget.checked)}
									/>
									<span class="dup-row-text">
										<span class="dup-row-date">
											{formatDate(rec.start)}
											{#if id === group.suggested_keep_id}
												<span class="dup-tag keep">{$_('hdhomerun.detail.remove_duplicates_suggested_keep')}</span>
											{/if}
											<span class="dup-tag">
												{rec.provider === 'hdhomerun'
													? $_('hdhomerun.detail.server_badge_hdhomerun')
													: $_('hdhomerun.detail.server_badge_builtin')}
											</span>
										</span>
										<span class="dup-row-meta">{recordingMeta(rec)}</span>
									</span>
								</label>
							</li>
						{/each}
					</ul>
				</section>
			{/each}
		{/if}
	</div>

	<div class="confirm-actions">
		<button type="button" class="btn btn-secondary" disabled={deleting} onclick={onClose}>
			{$_('hdhomerun.detail.remove_duplicates_cancel')}
		</button>
		{#if !loading && groups.length > 0}
			<button
				type="button"
				class="btn btn-danger"
				disabled={deleting || summary.count === 0}
				onclick={() => onConfirm([...selected])}
			>
				{#if deleting}
					{$_('hdhomerun.detail.deleting_button')}
				{:else}
					{$_('hdhomerun.detail.remove_duplicates_confirm', {
						values: { count: summary.count, size: formatBytes(summary.bytes) },
					})}
				{/if}
			</button>
		{/if}
	</div>
</div>

<style>
	.confirm-backdrop {
		position: fixed;
		inset: 0;
		z-index: 90;
		background: rgba(0, 0, 0, 0.65);
		backdrop-filter: blur(4px);
	}

	.confirm-dialog {
		position: fixed;
		z-index: 91;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: min(44rem, calc(100vw - 2rem));
		max-height: calc(100vh - 2rem);
		background: var(--color-surface, #1e2126);
		border: 1px solid var(--color-border, #2f333b);
		border-radius: 0.75rem;
		padding: 1.25rem;
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}

	.confirm-title {
		margin: 0;
		font-size: 1.15rem;
		font-weight: 700;
		color: var(--color-text, #f2f3f5);
	}

	.dialog-body {
		overflow-y: auto;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.confirm-message {
		margin: 0;
		font-size: 0.9rem;
		line-height: 1.45;
		color: var(--color-text-muted, #9aa0aa);
	}

	.dup-group {
		border: 1px solid var(--color-border, #2f333b);
		border-radius: 0.5rem;
		padding: 0.6rem 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.dup-group-header {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.6rem;
	}

	.dup-group-title {
		font-weight: 600;
		color: var(--color-text, #f2f3f5);
	}

	.dup-group-details {
		font-size: 0.8rem;
		color: var(--color-text-muted, #9aa0aa);
	}

	.dup-warning {
		margin: 0;
		font-size: 0.8rem;
		color: var(--color-warning, #e0a05a);
	}

	.dup-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.dup-row label {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		padding: 0.35rem 0.4rem;
		border-radius: 0.35rem;
		cursor: pointer;
	}

	.dup-row.checked label {
		background: rgba(224, 90, 90, 0.08);
	}

	.dup-row input {
		margin-top: 0.2rem;
	}

	.dup-row-text {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
		min-width: 0;
	}

	.dup-row-date {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.88rem;
		color: var(--color-text, #f2f3f5);
	}

	.dup-row-meta {
		font-size: 0.78rem;
		color: var(--color-text-muted, #9aa0aa);
	}

	.dup-tag {
		font-size: 0.7rem;
		padding: 0.05rem 0.35rem;
		border: 1px solid var(--color-border, #2f333b);
		border-radius: 0.3rem;
		color: var(--color-text-muted, #9aa0aa);
	}

	.dup-tag.keep {
		border-color: var(--color-accent, #4a9eda);
		color: var(--color-accent, #4a9eda);
	}

	.confirm-actions {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 0.6rem;
	}

	.btn {
		font-size: 0.85rem;
		font-weight: 600;
		padding: 0.45rem 0.9rem;
		border-radius: 0.45rem;
		cursor: pointer;
		border: 1px solid transparent;
		transition: opacity 0.15s ease;
	}

	.btn:hover {
		opacity: 0.9;
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-secondary {
		background: var(--color-bg, #14161a);
		border-color: var(--color-border, #2f333b);
		color: var(--color-text, #f2f3f5);
	}

	.btn-danger {
		background: var(--color-error, #e05a5a);
		color: #fff;
	}
</style>
