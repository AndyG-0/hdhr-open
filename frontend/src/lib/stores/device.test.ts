import { beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';

const { registerDevice, renameDevice: renameDeviceApi } = vi.hoisted(() => ({
	registerDevice: vi.fn(),
	renameDevice: vi.fn(),
}));
vi.mock('$lib/api', () => ({ api: { registerDevice, renameDevice: renameDeviceApi } }));

beforeEach(() => {
	vi.resetModules();
	registerDevice.mockReset();
	renameDeviceApi.mockReset();
});

describe('device store', () => {
	it('starts as null before ensureDevice resolves', async () => {
		const { device } = await import('./device');

		expect(get(device)).toBeNull();
	});

	it('ensureDevice registers the device and stores the result', async () => {
		const result = { id: 'dev1', name: 'New Device', is_new: true };
		registerDevice.mockResolvedValue(result);

		const { device, ensureDevice } = await import('./device');
		const returned = await ensureDevice();

		expect(get(device)).toEqual(result);
		expect(returned).toEqual(result);
	});

	it('renameDevice patches the name and stores the result', async () => {
		const result = { id: 'dev1', name: 'Kitchen Tablet' };
		renameDeviceApi.mockResolvedValue(result);

		const { device, renameDevice } = await import('./device');
		await renameDevice('Kitchen Tablet');

		expect(renameDeviceApi).toHaveBeenCalledWith('Kitchen Tablet');
		expect(get(device)).toEqual(result);
	});
});
