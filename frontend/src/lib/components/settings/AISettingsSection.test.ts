import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { testAIConnection, updateNetworkIntegration, listAIModels } = vi.hoisted(() => ({
	testAIConnection: vi.fn(),
	updateNetworkIntegration: vi.fn(),
	listAIModels: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { testAIConnection, updateNetworkIntegration, listAIModels },
}));

import AISettingsSection from './AISettingsSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	updateNetworkIntegration.mockResolvedValue({ settings: {} });
});

describe('AISettingsSection', () => {
	it('seeds the form from initialSettings', async () => {
		render(AISettingsSection, {
			initialSettings: {
				provider: 'anthropic',
				base_url: '',
				model: 'claude-sonnet-5',
				temperature: 0.4,
				system_prompt_custom: 'Be terse.',
				enable_recording_tools: true,
				has_api_key: true,
			},
		});

		await waitFor(() => expect(screen.getByLabelText('Model')).toHaveValue('claude-sonnet-5'));
		expect(screen.getByLabelText('API Key')).toHaveAttribute('placeholder', '(unchanged)');
		expect(screen.getByLabelText('Custom instructions')).toHaveValue('Be terse.');
		expect(screen.getByRole('checkbox')).toBeChecked();
	});

	it('shows the base URL field only for the custom provider', async () => {
		render(AISettingsSection, { initialSettings: { provider: 'openai', has_api_key: false } });

		await waitFor(() => expect(screen.queryByLabelText('Base URL')).not.toBeInTheDocument());

		await fireEvent.change(screen.getByLabelText('Provider'), { target: { value: 'custom' } });

		expect(screen.getByLabelText('Base URL')).toBeInTheDocument();
	});

	it('tests the connection', async () => {
		testAIConnection.mockResolvedValue({ ok: true, detail: 'gpt-4o reachable', error: null });
		render(AISettingsSection, { initialSettings: null });

		await fireEvent.click(screen.getByRole('button', { name: 'Test connection' }));

		expect(await screen.findByText('✓ gpt-4o reachable')).toBeInTheDocument();
	});

	it('shows a failed test-connection result', async () => {
		testAIConnection.mockResolvedValue({ ok: false, detail: null, error: 'Invalid API key' });
		render(AISettingsSection, { initialSettings: null });

		await fireEvent.click(screen.getByRole('button', { name: 'Test connection' }));

		expect(await screen.findByText('✗ Invalid API key')).toBeInTheDocument();
	});

	it('saves the entered key alongside the rest of the settings and clears the input', async () => {
		updateNetworkIntegration.mockResolvedValue({ settings: { has_api_key: true } });
		render(AISettingsSection, { initialSettings: { provider: 'openai', model: 'gpt-4o', has_api_key: false } });
		await waitFor(() => expect(screen.getByLabelText('Model')).toHaveValue('gpt-4o'));

		await fireEvent.input(screen.getByLabelText('API Key'), { target: { value: 'sk-secret' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() =>
			expect(updateNetworkIntegration).toHaveBeenCalledWith('ai', {
				provider: 'openai',
				base_url: '',
				model: 'gpt-4o',
				temperature: 0.7,
				system_prompt_custom: '',
				enable_recording_tools: false,
				api_key: 'sk-secret',
			}),
		);
		expect(screen.getByLabelText('API Key')).toHaveValue('');
	});

	it('does not send api_key when the field is left blank', async () => {
		render(AISettingsSection, { initialSettings: null });

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() => expect(updateNetworkIntegration).toHaveBeenCalled());
		const [, settings] = updateNetworkIntegration.mock.calls[0];
		expect(settings).not.toHaveProperty('api_key');
	});

	it('shows an error message when saving fails', async () => {
		updateNetworkIntegration.mockRejectedValue(new Error('network down'));
		render(AISettingsSection, { initialSettings: null });

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		expect(await screen.findByText('Could not save these settings.')).toBeInTheDocument();
	});

	it('disables the fetch-models button until an API key is present', async () => {
		render(AISettingsSection, { initialSettings: { provider: 'openai', has_api_key: false } });
		await waitFor(() => expect(screen.getByRole('button', { name: 'Fetch models' })).toBeDisabled());

		await fireEvent.input(screen.getByLabelText('API Key'), { target: { value: 'sk-secret' } });

		expect(screen.getByRole('button', { name: 'Fetch models' })).toBeEnabled();
	});

	it('leaves the fetch-models button enabled when a key is already saved', async () => {
		render(AISettingsSection, { initialSettings: { provider: 'openai', has_api_key: true } });

		await waitFor(() => expect(screen.getByRole('button', { name: 'Fetch models' })).toBeEnabled());
	});

	it('fetches models from the provider and shows how many were found', async () => {
		listAIModels.mockResolvedValue({ ok: true, models: ['gpt-4o', 'gpt-4o-mini'], error: null });
		render(AISettingsSection, { initialSettings: { provider: 'openai', has_api_key: true } });

		await fireEvent.click(screen.getByRole('button', { name: 'Fetch models' }));

		expect(await screen.findByText('2 models found.')).toBeInTheDocument();
		expect(listAIModels).toHaveBeenCalled();
	});

	it('shows an error when fetching models fails', async () => {
		listAIModels.mockResolvedValue({ ok: false, models: [], error: 'Invalid API key' });
		render(AISettingsSection, { initialSettings: { provider: 'openai', has_api_key: true } });

		await fireEvent.click(screen.getByRole('button', { name: 'Fetch models' }));

		expect(await screen.findByText('Invalid API key')).toBeInTheDocument();
	});
});
