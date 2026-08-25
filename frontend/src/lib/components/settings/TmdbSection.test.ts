import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

const { updateNetworkIntegration } = vi.hoisted(() => ({
	updateNetworkIntegration: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { updateNetworkIntegration },
}));

import TmdbSection from './TmdbSection.svelte';

describe('TmdbSection', () => {
	it('shows "(unchanged)" placeholder once an existing key is known', () => {
		render(TmdbSection, { initialHasApiKey: true });
		expect(screen.getByLabelText('API Key')).toHaveAttribute('placeholder', '(unchanged)');
	});

	it('shows no placeholder when no key is set yet', () => {
		render(TmdbSection, { initialHasApiKey: false });
		expect(screen.getByLabelText('API Key')).toHaveAttribute('placeholder', '');
	});

	it('saves the entered key and clears the input on success', async () => {
		updateNetworkIntegration.mockResolvedValue({ settings: { has_api_key: true } });
		render(TmdbSection, { initialHasApiKey: false });

		const input = screen.getByLabelText('API Key');
		await fireEvent.input(input, { target: { value: 'secret-key' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() =>
			expect(updateNetworkIntegration).toHaveBeenCalledWith('tmdb', { api_key: 'secret-key' }),
		);
		expect(input).toHaveValue('');
	});

	it('shows an error message when saving fails', async () => {
		updateNetworkIntegration.mockRejectedValue(new Error('network down'));
		render(TmdbSection, { initialHasApiKey: false });

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		expect(await screen.findByText('Could not save these settings.')).toBeInTheDocument();
	});
});
