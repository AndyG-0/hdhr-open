import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { updateUser, deleteUser, listUsers } = vi.hoisted(() => ({
	updateUser: vi.fn(),
	deleteUser: vi.fn(),
	listUsers: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { updateUser, deleteUser, listUsers },
}));

const { goto } = vi.hoisted(() => ({ goto: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto }));

const { logout } = vi.hoisted(() => ({ logout: vi.fn() }));
vi.mock('$lib/stores/user', async () => {
	const actual = await vi.importActual<typeof import('$lib/stores/user')>('$lib/stores/user');
	return { ...actual, logout };
});

import { user } from '$lib/stores/user';
import ProfileSection from './ProfileSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	listUsers.mockResolvedValue([{ id: 'u1', has_pin: false }]);
	user.set({ id: 'u1', name: 'Alice', avatar: '🐱', role: 'member' });
});

describe('ProfileSection', () => {
	it('seeds the name/avatar inputs from the current user', async () => {
		render(ProfileSection);
		expect(await screen.findByDisplayValue('Alice')).toBeInTheDocument();
		expect(screen.getByDisplayValue('🐱')).toBeInTheDocument();
	});

	it('saves profile changes', async () => {
		updateUser.mockResolvedValue({ id: 'u1', name: 'Bob', avatar: '🐱', role: 'member' });
		render(ProfileSection);

		const nameInput = await screen.findByDisplayValue('Alice');
		await fireEvent.input(nameInput, { target: { value: 'Bob' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

		await waitFor(() => expect(updateUser).toHaveBeenCalledWith({ name: 'Bob', avatar: '🐱' }));
	});

	it('rejects an invalid PIN before saving', async () => {
		render(ProfileSection);
		const pinInput = await screen.findByLabelText('PIN');
		await fireEvent.input(pinInput, { target: { value: '12' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

		expect(await screen.findByText('PIN must be 4-8 digits.')).toBeInTheDocument();
		expect(updateUser).not.toHaveBeenCalled();
	});

	it('deletes the profile after confirming', async () => {
		deleteUser.mockResolvedValue(undefined);
		logout.mockResolvedValue(undefined);
		render(ProfileSection);

		await screen.findByDisplayValue('Alice');
		await fireEvent.click(screen.getByRole('button', { name: 'Delete this profile' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Delete profile' }));

		await waitFor(() => expect(deleteUser).toHaveBeenCalled());
		expect(logout).toHaveBeenCalled();
		expect(goto).toHaveBeenCalledWith('/login');
	});
});
