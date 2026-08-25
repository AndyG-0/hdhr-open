import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { updatePreferences } = vi.hoisted(() => ({
	updatePreferences: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { updatePreferences },
}));

import LanguageSection from './LanguageSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	updatePreferences.mockResolvedValue({});
});

describe('LanguageSection', () => {
	it('saves the selected locale', async () => {
		render(LanguageSection);

		await fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'es' } });
		// svelte-i18n's locale store resolves the new dictionary asynchronously
		// before the store value itself settles — wait for that to land so
		// saveLocale() below reads the updated $locale, not the stale one.
		await waitFor(() => expect(screen.getByLabelText('Idioma')).toBeInTheDocument());
		await fireEvent.click(screen.getByRole('button', { name: 'Guardar idioma' }));

		await waitFor(() => expect(updatePreferences).toHaveBeenCalledWith({ locale: 'es' }));
		expect(await screen.findByText('Guardado.')).toBeInTheDocument();
	});
});
