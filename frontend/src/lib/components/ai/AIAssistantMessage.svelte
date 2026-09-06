<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'dompurify';
	import { _ } from 'svelte-i18n';
	import type { AIActionPreview } from '$lib/api';

	export interface ToolStatusEntry {
		tool: string;
		status: 'running' | 'done' | 'error';
		message?: string;
	}

	export interface ActionPreviewEntry {
		actionId: string;
		tool: string;
		preview: AIActionPreview;
		resolution: 'pending' | 'confirming' | 'confirmed' | 'cancelled' | 'failed';
	}

	interface Props {
		role: 'user' | 'assistant';
		text: string;
		toolStatuses?: ToolStatusEntry[];
		actionPreview?: ActionPreviewEntry | null;
		onConfirm?: (actionId: string) => void;
		onCancel?: (actionId: string) => void;
	}

	let { role, text, toolStatuses = [], actionPreview = null, onConfirm, onCancel }: Props = $props();

	// Model output is third-party API content, even though only a logged-in
	// household member ever sees it — sanitize before {@html}, same as any
	// other untrusted HTML would be treated.
	let renderedHtml = $derived(
		role === 'assistant' ? DOMPurify.sanitize(marked.parse(text || '', { async: false })) : '',
	);
</script>

<div class="message" class:user={role === 'user'} class:assistant={role === 'assistant'}>
	{#if role === 'user'}
		<p class="user-text">{text}</p>
	{:else}
		{#if text}
			<!-- eslint-disable-next-line svelte/no-at-html-tags -- renderedHtml is DOMPurify-sanitized immediately above -->
			<div class="assistant-text">{@html renderedHtml}</div>
		{/if}

		{#each toolStatuses as status (status.tool + status.status)}
			<div class="tool-chip" class:error={status.status === 'error'}>
				<span class="tool-name">{status.tool}</span>
				<span class="tool-state">
					{status.status === 'running' ? '…' : status.status === 'error' ? status.message || '✗' : '✓'}
				</span>
			</div>
		{/each}

		{#if actionPreview}
			<div class="action-card">
				<div class="action-card-title">{actionPreview.tool}</div>
				<dl class="action-card-fields">
					{#each Object.entries(actionPreview.preview) as [key, value] (key)}
						{#if value !== null && value !== undefined && value !== ''}
							<dt>{key}</dt>
							<dd>{value}</dd>
						{/if}
					{/each}
				</dl>
				{#if actionPreview.resolution === 'pending' || actionPreview.resolution === 'confirming'}
					<div class="action-card-buttons">
						<button
							class="confirm"
							disabled={actionPreview.resolution === 'confirming'}
							onclick={() => onConfirm?.(actionPreview!.actionId)}
						>
							{actionPreview.resolution === 'confirming' ? $_('ai_assistant.confirming') : $_('ai_assistant.confirm')}
						</button>
						<button
							class="cancel"
							disabled={actionPreview.resolution === 'confirming'}
							onclick={() => onCancel?.(actionPreview!.actionId)}
						>
							{$_('ai_assistant.cancel')}
						</button>
					</div>
				{:else if actionPreview.resolution === 'confirmed'}
					<p class="action-card-result ok">{$_('ai_assistant.action_confirmed')}</p>
				{:else if actionPreview.resolution === 'cancelled'}
					<p class="action-card-result">{$_('ai_assistant.action_cancelled')}</p>
				{:else if actionPreview.resolution === 'failed'}
					<p class="action-card-result error">{$_('ai_assistant.action_failed')}</p>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<style>
	.message {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		max-width: 90%;
	}

	.message.user {
		align-self: flex-end;
	}

	.message.assistant {
		align-self: flex-start;
	}

	.user-text {
		margin: 0;
		padding: 0.5rem 0.75rem;
		border-radius: 0.75rem;
		background: var(--color-accent);
		color: var(--color-surface);
		white-space: pre-wrap;
	}

	.assistant-text {
		padding: 0.5rem 0.75rem;
		border-radius: 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		color: var(--color-text);
	}

	.assistant-text :global(p:first-child) {
		margin-top: 0;
	}

	.assistant-text :global(p:last-child) {
		margin-bottom: 0;
	}

	.tool-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		align-self: flex-start;
		padding: 0.15rem 0.6rem;
		border-radius: 1rem;
		font-size: 0.8rem;
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		color: var(--color-text-muted);
	}

	.tool-chip.error {
		color: var(--color-error);
		border-color: var(--color-error);
	}

	.action-card {
		padding: 0.75rem;
		border-radius: 0.75rem;
		border: 1px solid var(--color-border);
		background: var(--color-bg);
	}

	.action-card-title {
		font-weight: 600;
		margin-bottom: 0.4rem;
		color: var(--color-text);
	}

	.action-card-fields {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.15rem 0.6rem;
		margin: 0 0 0.6rem;
		font-size: 0.85rem;
	}

	.action-card-fields dt {
		color: var(--color-text-muted);
	}

	.action-card-fields dd {
		margin: 0;
		color: var(--color-text);
		word-break: break-word;
	}

	.action-card-buttons {
		display: flex;
		gap: 0.5rem;
	}

	.action-card-buttons button {
		padding: 0.35rem 0.9rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		cursor: pointer;
	}

	.action-card-buttons .confirm {
		background: var(--color-accent);
		color: var(--color-surface);
		border-color: var(--color-accent);
	}

	.action-card-buttons .cancel {
		background: var(--color-bg);
		color: var(--color-text);
	}

	.action-card-result {
		margin: 0;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.action-card-result.ok {
		color: var(--color-success, #3fa34d);
	}

	.action-card-result.error {
		color: var(--color-error);
	}
</style>
