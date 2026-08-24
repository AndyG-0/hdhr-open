<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { HDHomeRunGuideEntry, RecordingRuleOptions } from '$lib/api';

	interface Props {
		airing: HDHomeRunGuideEntry;
		channelName: string;
		canRecordSeries: boolean;
		officialDvrActive: boolean;
		loading: boolean;
		onConfirm: (mode: 'episode' | 'series', options: RecordingRuleOptions) => void;
		onClose: () => void;
	}

	let { airing, channelName, canRecordSeries, officialDvrActive, loading, onConfirm, onClose }: Props =
		$props();

	let startPaddingMinutes = $state(0);
	let endPaddingMinutes = $state(0);
	let recentOnly = $state(false);
	let selectedServer = $state<'default' | 'builtin' | 'hdhomerun'>('default');
	let retentionMode = $state<'unlimited' | 'limited'>('unlimited');
	let retentionCount = $state(3);

	const isOfficialDvrTarget = $derived(
		selectedServer === 'hdhomerun' || (selectedServer === 'default' && officialDvrActive),
	);

	function buildOptions(): RecordingRuleOptions {
		return {
			startPadding: startPaddingMinutes ? startPaddingMinutes * 60 : undefined,
			endPadding: endPaddingMinutes ? endPaddingMinutes * 60 : undefined,
			recentOnly: recentOnly || undefined,
			maxEpisodesToKeep:
				!isOfficialDvrTarget && retentionMode === 'limited' && retentionCount > 0
					? retentionCount
					: undefined,
			server: selectedServer !== 'default' ? selectedServer : undefined,
		};
	}

	let dialogEl = $state<HTMLDivElement | null>(null);

	function handleWindowPointerDown(e: PointerEvent) {
		if (dialogEl && e.target instanceof Node && !dialogEl.contains(e.target)) onClose();
	}

	function handleWindowKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

<svelte:window onpointerdown={handleWindowPointerDown} onkeydown={handleWindowKeydown} />

<div class="options-backdrop"></div>
<div
	class="options-dialog"
	bind:this={dialogEl}
	role="dialog"
	aria-label={$_('hdhomerun.detail.recording_options_title')}
>
	<div class="options-header">
		<div class="options-title-group">
			<h3>{$_('hdhomerun.detail.recording_options_title')}</h3>
			<span class="options-subtitle">{airing.title} · {channelName}</span>
		</div>
		<button class="options-close" onclick={onClose} aria-label={$_('common.cancel')}>✕</button>
	</div>

	<div class="options-body">
		<label>
			{$_('hdhomerun.detail.server_label')}
			<select bind:value={selectedServer} aria-label={$_('hdhomerun.detail.server_label')}>
				<option value="default">{$_('hdhomerun.detail.server_default')}</option>
				<option value="builtin">{$_('hdhomerun.detail.server_builtin')}</option>
				<option value="hdhomerun">{$_('hdhomerun.detail.server_hdhomerun')}</option>
			</select>
		</label>

		<label>
			{$_('hdhomerun.detail.start_padding_label')}
			<input type="number" min="0" step="1" bind:value={startPaddingMinutes} />
		</label>

		<label>
			{$_('hdhomerun.detail.end_padding_label')}
			<input type="number" min="0" step="1" bind:value={endPaddingMinutes} />
		</label>

		<label class="checkbox">
			<input type="checkbox" bind:checked={recentOnly} />
			{$_('hdhomerun.detail.new_episodes_only_label')}
		</label>

		{#if isOfficialDvrTarget}
			<p class="hint">{$_('hdhomerun.detail.retention_official_dvr_note')}</p>
		{:else}
			<div class="retention-field">
				<span class="retention-label">{$_('hdhomerun.detail.retention_label')}</span>
				<div class="retention-choices">
					<label class="radio">
						<input type="radio" name="retention-mode" value="unlimited" bind:group={retentionMode} />
						{$_('hdhomerun.detail.retention_unlimited')}
					</label>
					<label class="radio">
						<input type="radio" name="retention-mode" value="limited" bind:group={retentionMode} />
						{$_('hdhomerun.detail.retention_keep_last', { values: { count: retentionCount } })}
					</label>
				</div>
				{#if retentionMode === 'limited'}
					<input
						type="number"
						min="1"
						step="1"
						class="retention-count"
						bind:value={retentionCount}
						aria-label={$_('hdhomerun.detail.retention_label')}
					/>
				{/if}
			</div>
		{/if}
	</div>

	<div class="options-footer">
		<button
			class="options-button"
			disabled={loading}
			onclick={() => onConfirm('episode', buildOptions())}
		>
			🔴 {$_('hdhomerun.detail.record_episode')}
		</button>
		{#if canRecordSeries}
			<button
				class="options-button primary"
				disabled={loading}
				onclick={() => onConfirm('series', buildOptions())}
			>
				{$_('hdhomerun.detail.record_series')}
			</button>
		{/if}
	</div>
</div>

<style>
	.options-backdrop {
		position: fixed;
		inset: 0;
		z-index: 60;
		background: rgba(0, 0, 0, 0.45);
	}

	.options-dialog {
		position: fixed;
		z-index: 61;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: min(22rem, calc(100vw - 2rem));
		max-height: calc(100vh - 2rem);
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.75rem;
		box-shadow: 0 0.75rem 2rem rgba(0, 0, 0, 0.3);
		padding: 1rem;
		gap: 0.75rem;
	}

	.options-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.options-title-group {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		min-width: 0;
	}

	.options-header h3 {
		margin: 0;
		font-size: 1rem;
	}

	.options-subtitle {
		font-size: 0.8rem;
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.options-close {
		background: none;
		border: none;
		color: var(--color-text-muted);
		font-size: 1rem;
		cursor: pointer;
		flex-shrink: 0;
	}

	.options-body {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.options-body label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.85rem;
		color: var(--color-text);
	}

	.options-body label.checkbox,
	.options-body label.radio {
		flex-direction: row;
		align-items: center;
		gap: 0.4rem;
	}

	.options-body input[type='number'] {
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: 0.35rem;
		padding: 0.4rem 0.5rem;
		color: var(--color-text);
		font-size: 0.85rem;
	}

	.hint {
		font-size: 0.8rem;
		color: var(--color-text-muted);
		margin: 0;
	}

	.retention-field {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.retention-label {
		font-size: 0.85rem;
		color: var(--color-text);
	}

	.retention-choices {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}

	.retention-choices .radio {
		font-size: 0.85rem;
	}

	.retention-count {
		width: 5rem;
	}

	.options-footer {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
	}

	.options-button {
		background: var(--color-surface-hover, rgba(0, 0, 0, 0.05));
		border: 1px solid var(--color-border);
		border-radius: 0.4rem;
		padding: 0.5rem 0.9rem;
		font-size: 0.85rem;
		color: var(--color-text);
		cursor: pointer;
	}

	.options-button:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.options-button.primary {
		background: var(--color-accent);
		border-color: var(--color-accent);
		color: var(--color-on-accent, #fff);
	}
</style>
