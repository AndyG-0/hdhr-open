import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { get } from 'svelte/store';

const { goto, createSetupAdmin } = vi.hoisted(() => ({
	goto: vi.fn(),
	createSetupAdmin: vi.fn(),
}));
vi.mock('$app/navigation', () => ({ goto }));
vi.mock('$lib/api', () => ({
	api: { createSetupAdmin },
	describeFetchError: () => 'server',
}));

import Page from './+page.svelte';
import { user } from '$lib/stores/user';
import { needsSetup } from '$lib/stores/setup';

describe('/setup +page.svelte', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		user.set(null);
		needsSetup.set(true);
	});

	it('creates the admin account, updates stores, and redirects home', async () => {
		createSetupAdmin.mockResolvedValue({ id: 'u1', name: 'Alice', avatar: null, role: 'admin' });
		render(Page);

		await fireEvent.input(screen.getByLabelText('Name'), { target: { value: 'Alice' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		await Promise.resolve();
		await Promise.resolve();

		expect(createSetupAdmin).toHaveBeenCalledWith('Alice', undefined, undefined);
		expect(get(user)).toEqual({ id: 'u1', name: 'Alice', avatar: null, role: 'admin' });
		expect(get(needsSetup)).toBe(false);
		expect(goto).toHaveBeenCalledWith('/');
	});

	it('rejects a malformed pin before calling the API', async () => {
		render(Page);

		await fireEvent.input(screen.getByLabelText('Name'), { target: { value: 'Alice' } });
		await fireEvent.input(screen.getByLabelText('PIN (optional)'), { target: { value: 'abc' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

		expect(screen.getByText('PIN must be 4-8 digits.')).toBeInTheDocument();
		expect(createSetupAdmin).not.toHaveBeenCalled();
	});

	it('shows an error message when account creation fails', async () => {
		createSetupAdmin.mockRejectedValue(new Error('boom'));
		render(Page);

		await fireEvent.input(screen.getByLabelText('Name'), { target: { value: 'Alice' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
		await Promise.resolve();
		await Promise.resolve();

		expect(screen.getByText('Could not create your account. Please try again.')).toBeInTheDocument();
	});
});
