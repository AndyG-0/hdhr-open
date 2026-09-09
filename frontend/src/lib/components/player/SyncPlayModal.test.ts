import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import SyncPlayModal from './SyncPlayModal.svelte';
import type { SyncPlayRoom } from '$lib/api';

describe('SyncPlayModal', () => {
	it('renders join and create options when not in a room', async () => {
		const onJoinRoom = vi.fn();
		const onCreateRoom = vi.fn();
		const onClose = vi.fn();

		render(SyncPlayModal, {
			props: {
				show: true,
				room: null,
				roomCode: null,
				onJoinRoom,
				onCreateRoom,
				onLeaveRoom: vi.fn(),
				onClose,
			},
		});

		expect(screen.getByText('SyncPlay Watch Party')).toBeInTheDocument();
		expect(screen.getByLabelText('Join with Room Code')).toBeInTheDocument();
		expect(screen.getByText('Create New Watch Room')).toBeInTheDocument();

		const input = screen.getByPlaceholderText('Enter 6-digit code');
		await fireEvent.input(input, { target: { value: 'abc123' } });

		const joinBtn = screen.getByRole('button', { name: 'Join' });
		await fireEvent.click(joinBtn);

		expect(onJoinRoom).toHaveBeenCalledWith('ABC123');

		const createBtn = screen.getByRole('button', { name: 'Create New Watch Room' });
		await fireEvent.click(createBtn);

		expect(onCreateRoom).toHaveBeenCalled();
	});

	it('renders active room state with participant list and copy button', async () => {
		const mockRoom: SyncPlayRoom = {
			room_code: 'XYZ789',
			created_at: 1000,
			host_session_id: 'sess_1',
			content: {
				type: 'channel',
				id: '4.1',
				title: 'NBC 4',
				channel_number: '4.1',
			},
			playback_state: {
				is_playing: true,
				position: 120.0,
				playback_rate: 1.0,
				updated_at: 1000,
			},
			participants: [
				{
					session_id: 'sess_1',
					user_name: 'Alice',
					is_host: true,
					is_ready: true,
					ping_ms: 12,
					position: 120.0,
					last_seen: 1000,
				},
				{
					session_id: 'sess_2',
					user_name: 'Bob',
					is_host: false,
					is_ready: true,
					ping_ms: 24,
					position: 119.5,
					last_seen: 1000,
				},
			],
		};

		const onLeaveRoom = vi.fn();
		const onTransferHost = vi.fn();

		render(SyncPlayModal, {
			props: {
				show: true,
				room: mockRoom,
				roomCode: 'XYZ789',
				participants: mockRoom.participants,
				isHost: true,
				pingMs: 12,
				status: 'in_sync',
				onJoinRoom: vi.fn(),
				onCreateRoom: vi.fn(),
				onLeaveRoom,
				onTransferHost,
				onClose: vi.fn(),
			},
		});

		expect(screen.getByText('XYZ789')).toBeInTheDocument();
		expect(screen.getByText('Alice')).toBeInTheDocument();
		expect(screen.getByText('Bob')).toBeInTheDocument();
		expect(screen.getByText('Host')).toBeInTheDocument();
		expect(screen.getByText('12ms')).toBeInTheDocument();
		expect(screen.getByText('24ms')).toBeInTheDocument();
		expect(screen.getByText('Synced')).toBeInTheDocument();

		const makeHostBtn = screen.getByRole('button', { name: 'Make Host' });
		await fireEvent.click(makeHostBtn);
		expect(onTransferHost).toHaveBeenCalledWith('sess_2');

		const leaveBtn = screen.getByRole('button', { name: 'Leave Room' });
		await fireEvent.click(leaveBtn);
		expect(onLeaveRoom).toHaveBeenCalled();
	});

	it('shows a session-ended message when the server closes the room', () => {
		const mockRoom: SyncPlayRoom = {
			room_code: 'XYZ789',
			created_at: 1000,
			host_session_id: 'sess_1',
			content: { type: 'channel', id: '4.1', title: 'NBC 4', channel_number: '4.1' },
			playback_state: { is_playing: false, position: 0, playback_rate: 1.0, updated_at: 1000 },
			participants: [],
		};

		render(SyncPlayModal, {
			props: {
				show: true,
				room: mockRoom,
				roomCode: 'XYZ789',
				participants: [],
				isHost: true,
				pingMs: 0,
				status: 'ended',
				onJoinRoom: vi.fn(),
				onCreateRoom: vi.fn(),
				onLeaveRoom: vi.fn(),
				onTransferHost: vi.fn(),
				onClose: vi.fn(),
			},
		});

		expect(screen.getByText('Session ended — please rejoin')).toBeInTheDocument();
	});
});
