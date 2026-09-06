import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { AIStreamCallbacks } from '$lib/api';

const { streamAIChat, confirmAIAction, cancelAIAction } = vi.hoisted(() => ({
	streamAIChat: vi.fn(),
	confirmAIAction: vi.fn(),
	cancelAIAction: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { streamAIChat, confirmAIAction, cancelAIAction },
}));

import { aiDrawerOpen, openAIDrawer } from '$lib/stores/ai-drawer';
import { get } from 'svelte/store';
import AIAssistantDrawer from './AIAssistantDrawer.svelte';

// Every scripted call replays a fixed sequence of the exact callback
// invocations `_run_chat` in backend/app/api/ai.py would trigger for that
// event sequence, then resolves — mirrors the backend's SSE contract
// without needing a real fetch/stream.
function scriptStream(...steps: ((cb: AIStreamCallbacks) => void)[]) {
	streamAIChat.mockImplementation(async (_body, cb: AIStreamCallbacks) => {
		for (const step of steps) step(cb);
	});
}

beforeEach(() => {
	vi.clearAllMocks();
	openAIDrawer();
	confirmAIAction.mockResolvedValue({ result: {} });
	cancelAIAction.mockResolvedValue({ ok: true });
});

describe('AIAssistantDrawer', () => {
	it('does not render when the drawer is closed', () => {
		aiDrawerOpen.set(false);
		render(AIAssistantDrawer);

		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
	});

	it('sends the typed message and streams the assistant reply in as tokens arrive', async () => {
		scriptStream(
			(cb) => cb.onToken?.('The '),
			(cb) => cb.onToken?.('Office is on now.'),
			(cb) => cb.onDone?.(),
		);
		render(AIAssistantDrawer);

		await fireEvent.input(screen.getByPlaceholderText("Ask about what's on, or to schedule a recording…"), {
			target: { value: "what's on channel 5" },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));

		expect(await screen.findByText("what's on channel 5")).toBeInTheDocument();
		expect(await screen.findByText('The Office is on now.')).toBeInTheDocument();
		expect(streamAIChat).toHaveBeenCalledTimes(1);
		const [body] = streamAIChat.mock.calls[0];
		expect(body.messages).toEqual([{ role: 'user', content: "what's on channel 5" }]);
	});

	it('resends the prior turn as structured tool_calls/tool entries, not just prose', async () => {
		streamAIChat.mockImplementationOnce(async (_body, cb: AIStreamCallbacks) => {
			cb.onToolCall?.('call_1', 'search_guide', { query: 'college football' });
			cb.onToolResult?.('call_1', 'search_guide', {
				results: [{ title: 'Alabama at Georgia' }],
				total_matches: 1,
			});
			cb.onToken?.('I found Alabama at Georgia.');
			cb.onDone?.();
		});
		streamAIChat.mockImplementationOnce(async (_body, cb: AIStreamCallbacks) => {
			cb.onToken?.('Scheduled it.');
			cb.onDone?.();
		});
		render(AIAssistantDrawer);

		const input = screen.getByPlaceholderText("Ask about what's on, or to schedule a recording…");
		await fireEvent.input(input, { target: { value: 'find college football games' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));
		expect(await screen.findByText('I found Alabama at Georgia.')).toBeInTheDocument();

		await fireEvent.input(input, { target: { value: 'all of those games' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));
		expect(await screen.findByText('Scheduled it.')).toBeInTheDocument();

		expect(streamAIChat).toHaveBeenCalledTimes(2);
		const [secondBody] = streamAIChat.mock.calls[1];
		expect(secondBody.messages).toEqual([
			{ role: 'user', content: 'find college football games' },
			{
				role: 'assistant',
				content: 'I found Alabama at Georgia.',
				tool_calls: [{ id: 'call_1', name: 'search_guide', arguments: { query: 'college football' } }],
			},
			{
				role: 'tool',
				tool_call_id: 'call_1',
				name: 'search_guide',
				content: { results: [{ title: 'Alabama at Georgia' }], total_matches: 1 },
			},
			{ role: 'user', content: 'all of those games' },
		]);
	});

	it('omits a dangling tool call with no captured result from the resent transcript', async () => {
		streamAIChat.mockImplementationOnce(async (_body, cb: AIStreamCallbacks) => {
			cb.onToolCall?.('call_1', 'search_guide', { query: 'college football' });
			// Stream errors before a matching onToolResult ever arrives.
			cb.onError?.('Lost connection to the AI provider.');
			cb.onDone?.();
		});
		streamAIChat.mockImplementationOnce(async (_body, cb: AIStreamCallbacks) => {
			cb.onToken?.('Trying again.');
			cb.onDone?.();
		});
		render(AIAssistantDrawer);

		const input = screen.getByPlaceholderText("Ask about what's on, or to schedule a recording…");
		await fireEvent.input(input, { target: { value: 'find college football games' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));
		expect(await screen.findByText('Lost connection to the AI provider.')).toBeInTheDocument();

		await fireEvent.input(input, { target: { value: 'try again' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));
		expect(await screen.findByText('Trying again.')).toBeInTheDocument();

		const [secondBody] = streamAIChat.mock.calls[1];
		expect(secondBody.messages).toEqual([
			{ role: 'user', content: 'find college football games' },
			{ role: 'user', content: 'try again' },
		]);
	});

	it('shows a running tool-status chip', async () => {
		scriptStream(
			(cb) => cb.onToolStatus?.('search_guide', 'running'),
			(cb) => cb.onDone?.(),
		);
		render(AIAssistantDrawer);

		await fireEvent.input(screen.getByPlaceholderText("Ask about what's on, or to schedule a recording…"), {
			target: { value: 'search the guide' },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));

		expect(await screen.findByText('search_guide')).toBeInTheDocument();
	});

	it('renders an action-preview card and confirms it only through confirmAIAction, never a DVR-mutating call', async () => {
		scriptStream(
			(cb) => cb.onActionPreview?.('action-1', 'schedule_recording', { title: 'The Office', channel: '5.1' }),
			(cb) => cb.onDone?.(),
		);
		render(AIAssistantDrawer);

		await fireEvent.input(screen.getByPlaceholderText("Ask about what's on, or to schedule a recording…"), {
			target: { value: 'record the office' },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));

		const confirmButton = await screen.findByRole('button', { name: 'Confirm' });
		await fireEvent.click(confirmButton);

		await waitFor(() => expect(confirmAIAction).toHaveBeenCalledWith('action-1'));
		expect(await screen.findByText('Done.')).toBeInTheDocument();
		// The drawer's only surface for mutating anything is confirmAIAction/
		// cancelAIAction — it must never call any other api function itself.
		expect(streamAIChat).toHaveBeenCalledTimes(1);
		expect(cancelAIAction).not.toHaveBeenCalled();
	});

	it('cancels a proposed action through cancelAIAction', async () => {
		scriptStream(
			(cb) => cb.onActionPreview?.('action-2', 'delete_recording', { title: 'Old Show' }),
			(cb) => cb.onDone?.(),
		);
		render(AIAssistantDrawer);

		await fireEvent.input(screen.getByPlaceholderText("Ask about what's on, or to schedule a recording…"), {
			target: { value: 'delete old show' },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));

		await fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

		await waitFor(() => expect(cancelAIAction).toHaveBeenCalledWith('action-2'));
		expect(await screen.findByText('Cancelled.')).toBeInTheDocument();
		expect(confirmAIAction).not.toHaveBeenCalled();
	});

	it('shows a stream error inline', async () => {
		scriptStream(
			(cb) => cb.onError?.("The AI assistant isn't configured yet."),
			(cb) => cb.onDone?.(),
		);
		render(AIAssistantDrawer);

		await fireEvent.input(screen.getByPlaceholderText("Ask about what's on, or to schedule a recording…"), {
			target: { value: 'hello' },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));

		expect(await screen.findByText("The AI assistant isn't configured yet.")).toBeInTheDocument();
	});

	it('closes on Escape', async () => {
		render(AIAssistantDrawer);
		expect(get(aiDrawerOpen)).toBe(true);

		await fireEvent.keyDown(window, { key: 'Escape' });

		expect(get(aiDrawerOpen)).toBe(false);
	});

	it('clears the transcript on New chat', async () => {
		scriptStream(
			(cb) => cb.onToken?.('Hi there.'),
			(cb) => cb.onDone?.(),
		);
		render(AIAssistantDrawer);

		await fireEvent.input(screen.getByPlaceholderText("Ask about what's on, or to schedule a recording…"), {
			target: { value: 'hello' },
		});
		await fireEvent.click(screen.getByRole('button', { name: 'Send' }));
		expect(await screen.findByText('Hi there.')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'New chat' }));

		expect(screen.queryByText('Hi there.')).not.toBeInTheDocument();
	});
});
