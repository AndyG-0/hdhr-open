import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { updatePreferences, themes } = vi.hoisted(() => ({
	updatePreferences: vi.fn(),
	themes: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { updatePreferences, themes },
}));

import AppearanceSection from './AppearanceSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	updatePreferences.mockResolvedValue({});
	themes.mockResolvedValue({
		themes: [
			{ id: 'light', name: 'Light' },
			{ id: 'dark', name: 'Dark' },
		],
	});
});

describe('AppearanceSection', () => {
	it('loads theme names from the server', async () => {
		render(AppearanceSection);
		expect(await screen.findByText('Light')).toBeInTheDocument();
		expect(screen.getByText('Dark')).toBeInTheDocument();
	});

	it('saves the selected theme', async () => {
		render(AppearanceSection);
		await screen.findByText('Light');

		await fireEvent.change(screen.getByLabelText('Appearance'), { target: { value: 'dark' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save appearance' }));

		await waitFor(() => expect(updatePreferences).toHaveBeenCalledWith({ theme: 'dark' }));
		expect(await screen.findByText('Saved.')).toBeInTheDocument();
	});
});
