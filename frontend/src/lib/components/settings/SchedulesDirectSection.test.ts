import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const {
	testSchedulesDirectConnection,
	updateNetworkIntegration,
	getSchedulesDirectStations,
	getSchedulesDirectHeadends,
	addSchedulesDirectLineup,
	deleteSchedulesDirectLineup,
	getSchedulesDirectLineups,
} = vi.hoisted(() => ({
	testSchedulesDirectConnection: vi.fn(),
	updateNetworkIntegration: vi.fn(),
	getSchedulesDirectStations: vi.fn(),
	getSchedulesDirectHeadends: vi.fn(),
	addSchedulesDirectLineup: vi.fn(),
	deleteSchedulesDirectLineup: vi.fn(),
	getSchedulesDirectLineups: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: {
		testSchedulesDirectConnection,
		updateNetworkIntegration,
		getSchedulesDirectStations,
		getSchedulesDirectHeadends,
		addSchedulesDirectLineup,
		deleteSchedulesDirectLineup,
		getSchedulesDirectLineups,
	},
}));

import SchedulesDirectSection from './SchedulesDirectSection.svelte';

beforeEach(() => {
	vi.clearAllMocks();
	updateNetworkIntegration.mockResolvedValue({ settings: { has_password: true } });
	getSchedulesDirectStations.mockResolvedValue([]);
});

describe('SchedulesDirectSection', () => {
	it('seeds the username input from initialUsername', async () => {
		render(SchedulesDirectSection, {
			initialUsername: 'someuser',
			initialHasPassword: true,
			onStationsChanged: vi.fn(),
		});

		await waitFor(() => expect(screen.getByPlaceholderText('username')).toHaveValue('someuser'));
	});

	it('tests the connection and shows the result', async () => {
		testSchedulesDirectConnection.mockResolvedValue({ ok: true, detail: { expires: null, lineups: [] }, error: null });
		render(SchedulesDirectSection, { initialUsername: '', initialHasPassword: false, onStationsChanged: vi.fn() });

		await fireEvent.click(screen.getByRole('button', { name: 'Test Connection' }));

		expect(await screen.findByText('✓ OK')).toBeInTheDocument();
	});

	it('saves settings and notifies onStationsChanged', async () => {
		const onStationsChanged = vi.fn();
		getSchedulesDirectStations.mockResolvedValue([{ station_id: 's1', name: 'Station 1' }]);
		render(SchedulesDirectSection, { initialUsername: 'someuser', initialHasPassword: false, onStationsChanged });

		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));

		await waitFor(() =>
			expect(updateNetworkIntegration).toHaveBeenCalledWith('schedules_direct', { username: 'someuser' }),
		);
		await waitFor(() => expect(onStationsChanged).toHaveBeenCalledWith([{ station_id: 's1', name: 'Station 1' }]));
	});

	it('adds a lineup found via headend search and notifies onStationsChanged', async () => {
		const onStationsChanged = vi.fn();
		getSchedulesDirectHeadends.mockResolvedValue([
			{ headend: 'h1', lineups: [{ lineup: 'USA-TEST-X', name: 'Test Lineup', transport: 'Cable' }] },
		]);
		getSchedulesDirectStations.mockResolvedValue([{ station_id: 's2', name: 'Station 2' }]);
		render(SchedulesDirectSection, { initialUsername: '', initialHasPassword: false, onStationsChanged });

		await fireEvent.input(screen.getByPlaceholderText('e.g. 90210'), { target: { value: '90210' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Search Lineups' }));
		expect(await screen.findByText('Test Lineup (USA-TEST-X)')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: 'Add Lineup' }));

		await waitFor(() => expect(addSchedulesDirectLineup).toHaveBeenCalledWith('USA-TEST-X'));
		await waitFor(() => expect(onStationsChanged).toHaveBeenCalledWith([{ station_id: 's2', name: 'Station 2' }]));
	});
});
