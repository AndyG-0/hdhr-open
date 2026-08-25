import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { updateSettings } = vi.hoisted(() => ({
	updateSettings: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { updateSettings },
}));

import TimezoneSection from './TimezoneSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	updateSettings.mockResolvedValue({});
});

describe('TimezoneSection', () => {
	it('seeds the select from initialTimezone', async () => {
		render(TimezoneSection, { initialTimezone: 'America/New_York' });
		await waitFor(() => expect(screen.getByRole('combobox')).toHaveValue('America/New_York'));
	});

	it('saves the selected timezone', async () => {
		render(TimezoneSection, { initialTimezone: 'UTC' });
		await fireEvent.click(screen.getByRole('button', { name: 'Save timezone' }));

		await waitFor(() => expect(updateSettings).toHaveBeenCalledWith({ timezone: 'UTC' }));
		expect(await screen.findByText('Saved.')).toBeInTheDocument();
	});

	it('shows an error message when saving fails', async () => {
		updateSettings.mockRejectedValue(new Error('boom'));
		render(TimezoneSection, { initialTimezone: 'UTC' });

		await fireEvent.click(screen.getByRole('button', { name: 'Save timezone' }));

		expect(await screen.findByText('Could not save timezone.')).toBeInTheDocument();
	});
});
