import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { listHouseholdUsers, updateUserRole, removeHouseholdUser } = vi.hoisted(() => ({
	listHouseholdUsers: vi.fn(),
	updateUserRole: vi.fn(),
	removeHouseholdUser: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { listHouseholdUsers, updateUserRole, removeHouseholdUser },
}));

import { user } from '$lib/stores/user';
import HouseholdMembersSection from './HouseholdMembersSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	user.set({ id: 'u1', name: 'Admin', avatar: null, role: 'admin' });
});

describe('HouseholdMembersSection', () => {
	it('loads and renders household members, marking the current user', async () => {
		listHouseholdUsers.mockResolvedValue([
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '' },
			{ id: 'u2', name: 'Member', role: 'member', avatar: '' },
		]);
		render(HouseholdMembersSection);

		expect(await screen.findByText('Member')).toBeInTheDocument();
		expect(screen.getByText('(you)')).toBeInTheDocument();
	});

	it('promotes a member to admin', async () => {
		listHouseholdUsers.mockResolvedValue([
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '' },
			{ id: 'u2', name: 'Member', role: 'member', avatar: '' },
		]);
		updateUserRole.mockResolvedValue({ id: 'u2', name: 'Member', role: 'admin', avatar: '' });
		render(HouseholdMembersSection);

		await screen.findByText('Member');
		await fireEvent.click(screen.getByRole('button', { name: 'Promote to admin' }));

		await waitFor(() => expect(updateUserRole).toHaveBeenCalledWith('u2', 'admin'));
	});

	it('removes a member after confirming', async () => {
		listHouseholdUsers.mockResolvedValue([
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '' },
			{ id: 'u2', name: 'Member', role: 'member', avatar: '' },
		]);
		removeHouseholdUser.mockResolvedValue(undefined);
		render(HouseholdMembersSection);

		await screen.findByText('Member');
		await fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Remove' }));

		await waitFor(() => expect(removeHouseholdUser).toHaveBeenCalledWith('u2'));
		await waitFor(() => expect(screen.queryByText('Member')).not.toBeInTheDocument());
	});

	it('shows an error message when loading fails', async () => {
		listHouseholdUsers.mockRejectedValue(new Error('boom'));
		render(HouseholdMembersSection);

		expect(await screen.findByText('Could not load household members.')).toBeInTheDocument();
	});
});
