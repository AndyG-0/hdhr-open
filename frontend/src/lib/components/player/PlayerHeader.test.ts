import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE_URL: 'http://api.test' },
}));

import PlayerHeader from './PlayerHeader.svelte';

describe('PlayerHeader.svelte', () => {
	it('renders title, channel number, and subtitle', () => {
		render(PlayerHeader, {
			props: {
				title: 'Evening News',
				subtitle: 'Local Stories',
				channelNumber: '4.1',
				channelName: 'KDFW',
				showAirPlayPicker: vi.fn(),
				buildCastContentUrl: vi.fn(),
				onClose: vi.fn(),
			},
		});

		expect(screen.getByText('Evening News')).toBeInTheDocument();
		expect(screen.getByText('Local Stories')).toBeInTheDocument();
		expect(screen.getByText('4.1')).toBeInTheDocument();
	});

	it('triggers onClose when close button is clicked', async () => {
		const onClose = vi.fn();
		render(PlayerHeader, {
			props: {
				title: 'Evening News',
				showAirPlayPicker: vi.fn(),
				buildCastContentUrl: vi.fn(),
				onClose,
			},
		});

		const closeBtn = screen.getByRole('button', { name: /Close player/i });
		await fireEvent.click(closeBtn);

		expect(onClose).toHaveBeenCalled();
	});

	it('renders AirPlay button and calls showAirPlayPicker when clicked', async () => {
		const showAirPlayPicker = vi.fn();
		render(PlayerHeader, {
			props: {
				title: 'Evening News',
				airplayAvailable: true,
				showAirPlayPicker,
				buildCastContentUrl: vi.fn(),
				onClose: vi.fn(),
			},
		});

		const airplayBtn = screen.getByRole('button', { name: /AirPlay/i });
		expect(airplayBtn).toBeInTheDocument();

		await fireEvent.click(airplayBtn);
		expect(showAirPlayPicker).toHaveBeenCalled();
	});

	it('renders Popout button and triggers onPopout when provided', async () => {
		const onPopout = vi.fn();
		render(PlayerHeader, {
			props: {
				title: 'Evening News',
				onPopout,
				showAirPlayPicker: vi.fn(),
				buildCastContentUrl: vi.fn(),
				onClose: vi.fn(),
			},
		});

		const popoutBtn = screen.getByRole('button', { name: /Popout player/i });
		await fireEvent.click(popoutBtn);

		expect(onPopout).toHaveBeenCalled();
	});

	it('renders SyncPlay button and triggers onToggleSyncPlay when provided', async () => {
		const onToggleSyncPlay = vi.fn();
		render(PlayerHeader, {
			props: {
				title: 'Evening News',
				syncPlayActive: true,
				syncPlayParticipantsCount: 3,
				onToggleSyncPlay,
				showAirPlayPicker: vi.fn(),
				buildCastContentUrl: vi.fn(),
				onClose: vi.fn(),
			},
		});

		const syncPlayBtn = screen.getByRole('button', { name: /SyncPlay/i });
		expect(syncPlayBtn).toBeInTheDocument();
		expect(screen.getByText('3')).toBeInTheDocument();

		await fireEvent.click(syncPlayBtn);
		expect(onToggleSyncPlay).toHaveBeenCalled();
	});

	it('renders MultiView button and triggers onToggleMultiView when provided', async () => {
		const onToggleMultiView = vi.fn();
		render(PlayerHeader, {
			props: {
				title: 'Evening News',
				onToggleMultiView,
				showAirPlayPicker: vi.fn(),
				buildCastContentUrl: vi.fn(),
				onClose: vi.fn(),
			},
		});

		const multiViewBtn = screen.getByRole('button', { name: /Multi-View/i });
		await fireEvent.click(multiViewBtn);

		expect(onToggleMultiView).toHaveBeenCalled();
	});
});
