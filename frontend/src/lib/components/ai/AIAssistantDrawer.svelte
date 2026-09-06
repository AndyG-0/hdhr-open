<script lang="ts">
	import { api, type AIChatMessage, type AIToolCallArguments, type AIToolResultContent } from '$lib/api';
	import { _ } from 'svelte-i18n';
	import { aiDrawerOpen, closeAIDrawer } from '$lib/stores/ai-drawer';
	import AIAssistantMessage, { type ToolStatusEntry, type ActionPreviewEntry } from './AIAssistantMessage.svelte';

	// Captured alongside the display-only `toolStatuses` so a later turn can
	// resend the exact structured tool call/result — not just the prose the
	// assistant wrote about it — letting the model resolve a follow-up like
	// "all of those games" against real data instead of re-searching.
	interface ToolCallRecord {
		id: string;
		name: string;
		arguments: AIToolCallArguments;
		result?: AIToolResultContent;
	}

	interface ChatTurn {
		role: 'user' | 'assistant';
		text: string;
		toolStatuses: ToolStatusEntry[];
		actionPreview: ActionPreviewEntry | null;
		toolCalls: ToolCallRecord[];
	}

	// Rebuilds the wire transcript from prior turns: a tool-calling assistant
	// turn is resent as its `tool_calls` entry followed by one `tool` entry
	// per call that actually got a result (a call left dangling by a stream
	// error is dropped rather than resent with no matching result).
	function toWireMessages(turns: ChatTurn[]): AIChatMessage[] {
		const wire: AIChatMessage[] = [];
		for (const turn of turns) {
			if (turn.role === 'user') {
				if (turn.text) wire.push({ role: 'user', content: turn.text });
				continue;
			}
			const resolvedCalls = turn.toolCalls.filter(
				(c): c is ToolCallRecord & { result: AIToolResultContent } => c.result !== undefined,
			);
			if (resolvedCalls.length === 0) {
				if (turn.text) wire.push({ role: 'assistant', content: turn.text });
				continue;
			}
			wire.push({
				role: 'assistant',
				content: turn.text,
				tool_calls: resolvedCalls.map((c) => ({ id: c.id, name: c.name, arguments: c.arguments })),
			});
			for (const call of resolvedCalls) {
				wire.push({ role: 'tool', tool_call_id: call.id, name: call.name, content: call.result });
			}
		}
		return wire;
	}

	let messages = $state<ChatTurn[]>([]);
	let inputValue = $state('');
	let sending = $state(false);
	let errorText = $state<string | null>(null);
	let dialogEl = $state<HTMLDivElement | null>(null);
	let messagesEl = $state<HTMLDivElement | null>(null);

	$effect(() => {
		// Re-run whenever the transcript changes so a new token/turn keeps the
		// view pinned to the bottom.
		void messages.length;
		void messages.at(-1)?.text;
		if (messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
	});

	function handleWindowPointerDown(e: PointerEvent) {
		if ($aiDrawerOpen && dialogEl && e.target instanceof Node && !dialogEl.contains(e.target)) closeAIDrawer();
	}

	function handleWindowKeydown(e: KeyboardEvent) {
		if ($aiDrawerOpen && e.key === 'Escape') closeAIDrawer();
	}

	function newChat() {
		messages = [];
		errorText = null;
	}

	async function send() {
		const content = inputValue.trim();
		if (!content || sending) return;

		inputValue = '';
		errorText = null;
		const transcript = toWireMessages(messages);
		transcript.push({ role: 'user', content });

		messages.push({ role: 'user', text: content, toolStatuses: [], actionPreview: null, toolCalls: [] });
		messages.push({ role: 'assistant', text: '', toolStatuses: [], actionPreview: null, toolCalls: [] });
		// Index, not a reference to the pushed object — $state deeply proxies
		// array contents on push, so the pre-push object reference wouldn't be
		// the reactive one the template reads from.
		const assistantIndex = messages.length - 1;
		sending = true;

		await api.streamAIChat(
			{
				messages: transcript,
				context: {
					now: new Date().toISOString(),
					timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
				},
			},
			{
				onToken: (text) => {
					messages[assistantIndex].text += text;
				},
				onToolCall: (id, tool, args) => {
					messages[assistantIndex].toolCalls.push({ id, name: tool, arguments: args });
				},
				onToolResult: (id, _tool, content) => {
					const record = messages[assistantIndex].toolCalls.find((c) => c.id === id);
					if (record) record.result = content;
				},
				onToolStatus: (tool, status, message) => {
					const toolStatuses = messages[assistantIndex].toolStatuses;
					const existing = toolStatuses.find((s) => s.tool === tool);
					if (existing) {
						existing.status = status;
						existing.message = message;
					} else {
						toolStatuses.push({ tool, status, message });
					}
				},
				onActionPreview: (actionId, tool, preview) => {
					messages[assistantIndex].actionPreview = { actionId, tool, preview, resolution: 'pending' };
				},
				onError: (message) => {
					errorText = message;
				},
				onDone: () => {
					sending = false;
				},
			},
		);
		sending = false;
	}

	function findActionPreview(actionId: string): ActionPreviewEntry | undefined {
		for (const turn of messages) {
			if (turn.actionPreview?.actionId === actionId) return turn.actionPreview;
		}
		return undefined;
	}

	async function confirmAction(actionId: string) {
		const entry = findActionPreview(actionId);
		if (!entry) return;
		entry.resolution = 'confirming';
		try {
			await api.confirmAIAction(actionId);
			entry.resolution = 'confirmed';
		} catch {
			entry.resolution = 'failed';
		}
	}

	async function cancelAction(actionId: string) {
		const entry = findActionPreview(actionId);
		if (!entry) return;
		try {
			await api.cancelAIAction(actionId);
		} catch {
			// Best-effort — the pending action expires from the server-side
			// cache on its own after its TTL either way.
		}
		entry.resolution = 'cancelled';
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			send();
		}
	}
</script>

<svelte:window onpointerdown={handleWindowPointerDown} onkeydown={handleWindowKeydown} />

{#if $aiDrawerOpen}
	<div class="ai-backdrop"></div>
	<div class="ai-drawer" bind:this={dialogEl} role="dialog" aria-label={$_('ai_assistant.title')}>
		<div class="ai-drawer-header">
			<h2>{$_('ai_assistant.title')}</h2>
			<div class="ai-drawer-header-actions">
				<button class="ai-new-chat" onclick={newChat}>{$_('ai_assistant.new_chat')}</button>
				<button class="ai-close" onclick={closeAIDrawer} aria-label={$_('common.close')}>✕</button>
			</div>
		</div>

		<div class="ai-messages" bind:this={messagesEl}>
			{#if messages.length === 0}
				<p class="ai-empty-hint">{$_('ai_assistant.placeholder')}</p>
			{/if}
			{#each messages as turn, i (i)}
				<AIAssistantMessage
					role={turn.role}
					text={turn.text}
					toolStatuses={turn.toolStatuses}
					actionPreview={turn.actionPreview}
					onConfirm={confirmAction}
					onCancel={cancelAction}
				/>
			{/each}
			{#if sending && messages.at(-1)?.text === '' && (messages.at(-1)?.toolStatuses.length ?? 0) === 0}
				<p class="ai-thinking">{$_('ai_assistant.thinking')}</p>
			{/if}
		</div>

		{#if errorText}
			<p class="ai-error">{errorText}</p>
		{/if}

		<div class="ai-input-row">
			<textarea
				bind:value={inputValue}
				onkeydown={handleKeydown}
				placeholder={$_('ai_assistant.placeholder')}
				rows="2"
				disabled={sending}></textarea>
			<button class="ai-send" disabled={sending || !inputValue.trim()} onclick={send}>
				{$_('ai_assistant.send')}
			</button>
		</div>
	</div>
{/if}

<style>
	.ai-backdrop {
		position: fixed;
		inset: 0;
		z-index: 60;
		background: rgba(0, 0, 0, 0.3);
	}

	.ai-drawer {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		z-index: 61;
		width: min(420px, 100vw);
		display: flex;
		flex-direction: column;
		background: var(--color-surface);
		border-left: 1px solid var(--color-border);
	}

	.ai-drawer-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 1rem;
		border-bottom: 1px solid var(--color-border);
	}

	.ai-drawer-header h2 {
		margin: 0;
		font-size: 1.1rem;
		color: var(--color-text);
	}

	.ai-drawer-header-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.ai-new-chat {
		background: none;
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.3rem 0.6rem;
		font-size: 0.8rem;
		color: var(--color-text-muted);
		cursor: pointer;
	}

	.ai-close {
		background: none;
		border: none;
		font-size: 1rem;
		color: var(--color-text-muted);
		cursor: pointer;
	}

	.ai-messages {
		flex: 1;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding: 1rem;
	}

	.ai-empty-hint,
	.ai-thinking {
		color: var(--color-text-muted);
		font-size: 0.9rem;
	}

	.ai-error {
		margin: 0 1rem;
		color: var(--color-error);
		font-size: 0.85rem;
	}

	.ai-input-row {
		display: flex;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--color-border);
	}

	.ai-input-row textarea {
		flex: 1;
		resize: none;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		background: var(--color-bg);
		color: var(--color-text);
		padding: 0.5rem;
		font: inherit;
	}

	.ai-send {
		align-self: flex-end;
		background: var(--color-accent);
		color: var(--color-surface);
		border: none;
		border-radius: 0.5rem;
		padding: 0.5rem 1rem;
		cursor: pointer;
	}

	.ai-send:disabled {
		opacity: 0.5;
		cursor: default;
	}
</style>
