<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { HDHomeRunChannel } from '$lib/api';

	export interface KeywordRuleOptions {
		title: string;
		titleMatchMode: 'exact' | 'contains';
		keywordQuery?: string;
		channel?: string;
		startPadding?: number;
		endPadding?: number;
		recentOnly?: boolean;
		maxEpisodesToKeep?: number;
	}

	interface Props {
		channels?: HDHomeRunChannel[];
		loading: boolean;
		onConfirm: (options: KeywordRuleOptions) => void;
		onClose: () => void;
	}

	let { channels = [], loading, onConfirm, onClose }: Props = $props();

	let title = $state('');
	let titleMatchMode = $state<'exact' | 'contains'>('exact');
	let keywordQuery = $state('');
	let channelMode = $state<'any' | 'custom'>('any');
	let selectedCustomChannels = $state<string[]>([]);
	let startPaddingMinutes = $state(0);
	let endPaddingMinutes = $state(0);
	let recentOnly = $state(false);
	let retentionMode = $state<'unlimited' | 'limited'>('unlimited');
	let retentionCount = $state(3);

	const canSubmit = $derived(title.trim().length > 0);

	function getEffectiveChannel(): string | undefined {
		if (channelMode === 'any') return undefined;
		if (channelMode === 'custom') {
			const selected = selectedCustomChannels.filter(Boolean);
			return selected.length > 0 ? selected.join('|') : undefined;
		}
		return undefined;
	}

	function submit() {
		if (!canSubmit) return;
		onConfirm({
			title: title.trim(),
			titleMatchMode,
			keywordQuery: keywordQuery.trim() || undefined,
			channel: getEffectiveChannel(),
			startPadding: startPaddingMinutes ? startPaddingMinutes * 60 : undefined,
			endPadding: endPaddingMinutes ? endPaddingMinutes * 60 : undefined,
			recentOnly: recentOnly || undefined,
			maxEpisodesToKeep: retentionMode === 'limited' && retentionCount > 0 ? retentionCount : undefined,
		});
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
	aria-label={$_('hdhomerun.detail.keyword_rule_title')}
>
	<div class="options-header">
		<h3>{$_('hdhomerun.detail.keyword_rule_title')}</h3>
		<button class="options-close" onclick={onClose} aria-label={$_('common.cancel')}>✕</button>
	</div>

	<div class="options-body">
		<label>
			{$_('hdhomerun.detail.keyword_rule_title_label')}
			<input
				type="text"
				bind:value={title}
				placeholder={$_('hdhomerun.detail.keyword_rule_title_placeholder')}
			/>
		</label>

		<div class="match-mode-field">
			<span class="match-mode-label">{$_('hdhomerun.detail.keyword_rule_match_mode_label')}</span>
			<label class="radio">
				<input type="radio" name="title-match-mode" value="exact" bind:group={titleMatchMode} />
				{$_('hdhomerun.detail.keyword_rule_match_exact')}
			</label>
			<label class="radio">
				<input type="radio" name="title-match-mode" value="contains" bind:group={titleMatchMode} />
				{$_('hdhomerun.detail.keyword_rule_match_contains')}
			</label>
		</div>

		<label>
			{$_('hdhomerun.detail.keyword_rule_keyword_label')}
			<input
				type="text"
				bind:value={keywordQuery}
				placeholder={$_('hdhomerun.detail.keyword_rule_keyword_placeholder')}
			/>
			<span class="hint">{$_('hdhomerun.detail.keyword_rule_keyword_hint')}</span>
		</label>

		{#if channels && channels.length > 0}
			<div class="channel-scope-field">
				<span class="channel-scope-label">{$_('hdhomerun.detail.channel_label')}</span>
				<div class="channel-scope-choices">
					<label class="radio">
						<input type="radio" name="keyword-channel-mode" value="any" bind:group={channelMode} />
						{$_('hdhomerun.detail.channel_mode_any')}
					</label>
					<label class="radio">
						<input type="radio" name="keyword-channel-mode" value="custom" bind:group={channelMode} />
						{$_('hdhomerun.detail.channel_mode_custom')}
					</label>
				</div>

				{#if channelMode === 'custom'}
					<div class="channel-picker-wrap">
						<span class="channel-picker-prompt">{$_('hdhomerun.detail.select_channels_prompt')}</span>
						<div class="channel-checklist" role="group" aria-label={$_('hdhomerun.detail.select_channels_prompt')}>
							{#each channels as ch}
								<label class="channel-check-item">
									<input
										type="checkbox"
										value={ch.channel_number}
										checked={selectedCustomChannels.includes(ch.channel_number)}
										onchange={(e) => {
											const checked = (e.currentTarget as HTMLInputElement).checked;
											if (checked) {
												if (!selectedCustomChannels.includes(ch.channel_number)) {
													selectedCustomChannels = [...selectedCustomChannels, ch.channel_number];
												}
											} else {
												selectedCustomChannels = selectedCustomChannels.filter((c) => c !== ch.channel_number);
											}
										}}
									/>
									<span class="channel-check-number">{ch.channel_number}</span>
									<span class="channel-check-name">{ch.name}</span>
								</label>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		{/if}

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
	</div>

	<div class="options-footer">
		<button class="options-button primary" disabled={loading || !canSubmit} onclick={submit}>
			{$_('hdhomerun.detail.keyword_rule_create')}
		</button>
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
		width: min(24rem, calc(100vw - 2rem));
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

	.options-header h3 {
		margin: 0;
		font-size: 1rem;
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

	.options-body input[type='number'],
	.options-body input[type='text'] {
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: 0.35rem;
		padding: 0.4rem 0.5rem;
		color: var(--color-text);
		font-size: 0.85rem;
	}

	.match-mode-field,
	.channel-scope-field,
	.retention-field {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.match-mode-label,
	.channel-scope-label,
	.retention-label {
		font-size: 0.85rem;
		color: var(--color-text);
	}

	.channel-scope-choices {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.channel-picker-wrap {
		margin-top: 0.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		background: rgba(0, 0, 0, 0.15);
		border: 1px solid var(--color-border);
		border-radius: 0.4rem;
		padding: 0.5rem;
	}

	.channel-picker-prompt {
		font-size: 0.78rem;
		color: var(--color-text-muted);
	}

	.channel-checklist {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		gap: 0.35rem;
		max-height: 9rem;
		overflow-y: auto;
		padding: 0.2rem 0;
	}

	.channel-check-item {
		display: flex !important;
		flex-direction: row !important;
		align-items: center;
		gap: 0.35rem !important;
		font-size: 0.8rem !important;
		cursor: pointer;
		padding: 0.2rem 0.3rem;
		border-radius: 0.25rem;
	}

	.channel-check-item:hover {
		background: rgba(255, 255, 255, 0.05);
	}

	.channel-check-number {
		font-weight: 600;
	}

	.channel-check-name {
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
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

	.hint {
		font-size: 0.75rem;
		color: var(--color-text-muted);
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
