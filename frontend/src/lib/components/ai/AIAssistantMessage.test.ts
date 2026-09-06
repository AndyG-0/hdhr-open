import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import AIAssistantMessage from './AIAssistantMessage.svelte';

describe('AIAssistantMessage', () => {
	it('renders a user turn as plain text, not markdown', () => {
		render(AIAssistantMessage, { role: 'user', text: '**not bold**' });

		expect(screen.getByText('**not bold**')).toBeInTheDocument();
	});

	it('renders assistant markdown as formatted HTML', () => {
		render(AIAssistantMessage, { role: 'assistant', text: 'Here is **The Office** at 8pm.' });

		const strong = screen.getByText('The Office');
		expect(strong.tagName).toBe('STRONG');
	});

	it('sanitizes script tags out of assistant markdown before rendering', () => {
		render(AIAssistantMessage, {
			role: 'assistant',
			text: 'Hello<script>window.__pwned = true;</script>',
		});

		expect(document.querySelector('script')).toBeNull();
		expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
	});

	it('shows a tool-status chip', () => {
		render(AIAssistantMessage, {
			role: 'assistant',
			text: '',
			toolStatuses: [{ tool: 'search_guide', status: 'running' }],
		});

		expect(screen.getByText('search_guide')).toBeInTheDocument();
	});

	it('renders an action-preview card with Confirm/Cancel wired to the given callbacks', async () => {
		const onConfirm = vi.fn();
		const onCancel = vi.fn();
		render(AIAssistantMessage, {
			role: 'assistant',
			text: '',
			actionPreview: {
				actionId: 'action-1',
				tool: 'schedule_recording',
				preview: { title: 'The Office', channel: '5.1' },
				resolution: 'pending',
			},
			onConfirm,
			onCancel,
		});

		expect(screen.getByText('schedule_recording')).toBeInTheDocument();
		expect(screen.getByText('The Office')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
		expect(onConfirm).toHaveBeenCalledWith('action-1');

		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(onCancel).toHaveBeenCalledWith('action-1');
	});

	it('shows a resolved state instead of buttons once confirmed', () => {
		render(AIAssistantMessage, {
			role: 'assistant',
			text: '',
			actionPreview: {
				actionId: 'action-1',
				tool: 'schedule_recording',
				preview: { title: 'The Office' },
				resolution: 'confirmed',
			},
		});

		expect(screen.getByText('Done.')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
	});
});
