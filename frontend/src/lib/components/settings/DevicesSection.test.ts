import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { listDevices, deleteDevice, renameDevice } = vi.hoisted(() => ({
	listDevices: vi.fn(),
	deleteDevice: vi.fn(),
	renameDevice: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { listDevices, deleteDevice, renameDevice },
}));

import { device } from '$lib/stores/device';
import DevicesSection from './DevicesSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	device.set({ id: 'd1', name: 'Living Room' });
	listDevices.mockResolvedValue([
		{ id: 'd1', name: 'Living Room' },
		{ id: 'd2', name: 'Bedroom' },
	]);
});

describe('DevicesSection', () => {
	it('loads and lists devices, marking the current one', async () => {
		render(DevicesSection);
		expect(await screen.findByText('Living Room')).toBeInTheDocument();
		expect(screen.getByText('Bedroom')).toBeInTheDocument();
		expect(screen.getByText('(This device)')).toBeInTheDocument();
	});

	it('renames the current device via the dialog', async () => {
		renameDevice.mockResolvedValue({ id: 'd1', name: 'Family Room' });
		listDevices.mockResolvedValueOnce([
			{ id: 'd1', name: 'Living Room' },
			{ id: 'd2', name: 'Bedroom' },
		]);
		render(DevicesSection);

		await screen.findByText('Living Room');
		await fireEvent.click(screen.getByRole('button', { name: 'Rename this device' }));

		const input = screen.getByRole('dialog').querySelector('input') as HTMLInputElement;
		await fireEvent.input(input, { target: { value: 'Family Room' } });

		listDevices.mockResolvedValueOnce([
			{ id: 'd1', name: 'Family Room' },
			{ id: 'd2', name: 'Bedroom' },
		]);
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() => expect(renameDevice).toHaveBeenCalledWith('Family Room'));
	});

	it('forgets another device after confirming', async () => {
		deleteDevice.mockResolvedValue(undefined);
		render(DevicesSection);

		await screen.findByText('Bedroom');
		await fireEvent.click(screen.getByRole('button', { name: 'Forget device' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Forget' }));

		await waitFor(() => expect(deleteDevice).toHaveBeenCalledWith('d2'));
		await waitFor(() => expect(screen.queryByText('Bedroom')).not.toBeInTheDocument());
	});
});
