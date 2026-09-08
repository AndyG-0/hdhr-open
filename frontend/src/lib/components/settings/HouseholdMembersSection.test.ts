import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { listHouseholdUsers, updateUserRole, removeHouseholdUser, createHouseholdUser, updateHouseholdUser } =
	vi.hoisted(() => ({
		listHouseholdUsers: vi.fn(),
		updateUserRole: vi.fn(),
		removeHouseholdUser: vi.fn(),
		createHouseholdUser: vi.fn(),
		updateHouseholdUser: vi.fn(),
	}));

vi.mock('$lib/api', () => ({
	api: {
		listHouseholdUsers,
		updateUserRole,
		removeHouseholdUser,
		createHouseholdUser,
		updateHouseholdUser,
	},
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
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '', has_pin: false, created_at: '2026-01-01' },
			{ id: 'u2', name: 'Member', role: 'member', avatar: '', has_pin: true, created_at: '2026-01-02' },
		]);
		render(HouseholdMembersSection);

		expect(await screen.findByText('Member')).toBeInTheDocument();
		expect(screen.getByText('(you)')).toBeInTheDocument();
		expect(screen.getByTitle('PIN is configured')).toBeInTheDocument();
	});

	it('adds a new household member', async () => {
		listHouseholdUsers.mockResolvedValue([
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '', has_pin: false, created_at: '2026-01-01' },
		]);
		createHouseholdUser.mockResolvedValue({
			id: 'u3',
			name: 'Charlie',
			avatar: '🦊',
			role: 'member',
			has_pin: true,
			created_at: '2026-01-03',
		});
		render(HouseholdMembersSection);

		await screen.findByText('Admin');
		await fireEvent.click(screen.getByRole('button', { name: '+ Add member' }));

		const form = screen.getByLabelText('Add member');
		const textInputs = form.querySelectorAll<HTMLInputElement>('input[type="text"]');
		const nameInput = textInputs[0];
		const avatarInput = textInputs[1];
		const pinInput = form.querySelector<HTMLInputElement>('input[type="password"]')!;

		await fireEvent.input(nameInput, { target: { value: 'Charlie' } });
		await fireEvent.input(avatarInput, { target: { value: '🦊' } });
		await fireEvent.input(pinInput, { target: { value: '1234' } });

		await fireEvent.click(screen.getByRole('button', { name: 'Create member' }));

		await waitFor(() =>
			expect(createHouseholdUser).toHaveBeenCalledWith({
				name: 'Charlie',
				avatar: '🦊',
				role: 'member',
				pin: '1234',
			}),
		);
		expect(await screen.findByText('Charlie')).toBeInTheDocument();
	});

	it('shows error if PIN format is invalid when adding a member', async () => {
		listHouseholdUsers.mockResolvedValue([
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '', has_pin: false, created_at: '2026-01-01' },
		]);
		render(HouseholdMembersSection);

		await screen.findByText('Admin');
		await fireEvent.click(screen.getByRole('button', { name: '+ Add member' }));

		const form = screen.getByLabelText('Add member');
		const nameInput = form.querySelector('input[placeholder="Alice"]') as HTMLInputElement;
		const pinInput = form.querySelector('input[type="password"]') as HTMLInputElement;

		await fireEvent.input(nameInput, { target: { value: 'Charlie' } });
		await fireEvent.input(pinInput, { target: { value: '12' } });

		await fireEvent.click(screen.getByRole('button', { name: 'Create member' }));

		expect(await screen.findByText('PIN must be 4-8 digits.')).toBeInTheDocument();
		expect(createHouseholdUser).not.toHaveBeenCalled();
	});

	it('edits an existing member and resets their PIN', async () => {
		listHouseholdUsers.mockResolvedValue([
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '', has_pin: false, created_at: '2026-01-01' },
			{ id: 'u2', name: 'Member', role: 'member', avatar: '🐱', has_pin: false, created_at: '2026-01-02' },
		]);
		updateHouseholdUser.mockResolvedValue({
			id: 'u2',
			name: 'Member Updated',
			role: 'member',
			avatar: '🐶',
			has_pin: true,
			created_at: '2026-01-02',
		});
		render(HouseholdMembersSection);

		await screen.findByText('Member');
		const editButtons = screen.getAllByRole('button', { name: 'Edit' });
		await fireEvent.click(editButtons[1]); // member2 edit button

		const editForm = screen.getByLabelText('Edit');
		const nameInput = editForm.querySelector('input[type="text"]') as HTMLInputElement;
		const pinInput = editForm.querySelector('input[type="password"]') as HTMLInputElement;

		await fireEvent.input(nameInput, { target: { value: 'Member Updated' } });
		await fireEvent.input(pinInput, { target: { value: '5678' } });

		await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

		await waitFor(() =>
			expect(updateHouseholdUser).toHaveBeenCalledWith('u2', {
				name: 'Member Updated',
				avatar: '🐱',
				role: 'member',
				pin: '5678',
			}),
		);
		expect(await screen.findByText('Member Updated')).toBeInTheDocument();
	});

	it('clears an existing PIN when editing a member', async () => {
		listHouseholdUsers.mockResolvedValue([
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '', has_pin: false, created_at: '2026-01-01' },
			{ id: 'u2', name: 'Member', role: 'member', avatar: '', has_pin: true, created_at: '2026-01-02' },
		]);
		updateHouseholdUser.mockResolvedValue({
			id: 'u2',
			name: 'Member',
			role: 'member',
			avatar: null,
			has_pin: false,
			created_at: '2026-01-02',
		});
		render(HouseholdMembersSection);

		await screen.findByText('Member');
		const editButtons = screen.getAllByRole('button', { name: 'Edit' });
		await fireEvent.click(editButtons[1]);

		const clearPinCheckbox = screen.getByRole('checkbox', { name: 'Remove PIN' });
		await fireEvent.click(clearPinCheckbox);

		await fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

		await waitFor(() =>
			expect(updateHouseholdUser).toHaveBeenCalledWith('u2', {
				name: 'Member',
				avatar: null,
				role: 'member',
				pin: '',
			}),
		);
	});

	it('promotes a member to admin', async () => {
		listHouseholdUsers.mockResolvedValue([
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '', has_pin: false, created_at: '2026-01-01' },
			{ id: 'u2', name: 'Member', role: 'member', avatar: '', has_pin: false, created_at: '2026-01-02' },
		]);
		updateUserRole.mockResolvedValue({
			id: 'u2',
			name: 'Member',
			role: 'admin',
			avatar: '',
			has_pin: false,
			created_at: '2026-01-02',
		});
		render(HouseholdMembersSection);

		await screen.findByText('Member');
		await fireEvent.click(screen.getByRole('button', { name: 'Promote to admin' }));

		await waitFor(() => expect(updateUserRole).toHaveBeenCalledWith('u2', 'admin'));
	});

	it('removes a member after confirming', async () => {
		listHouseholdUsers.mockResolvedValue([
			{ id: 'u1', name: 'Admin', role: 'admin', avatar: '', has_pin: false, created_at: '2026-01-01' },
			{ id: 'u2', name: 'Member', role: 'member', avatar: '', has_pin: false, created_at: '2026-01-02' },
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
