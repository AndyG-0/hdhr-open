import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { createSyncPlayController, type SyncPlayControllerCallbacks } from './syncplay-controller';
import type { SyncPlayRoom } from '$lib/api';

const { syncPlayWsUrl } = vi.hoisted(() => ({
	syncPlayWsUrl: vi.fn((roomCode: string) => `ws://api.test/ws/syncplay/${roomCode}`),
}));

vi.mock('$lib/api', () => ({
	api: {
		syncPlayWsUrl,
	},
}));

describe('syncplay-controller', () => {
	let mockWsInstances: MockWebSocket[] = [];

	class MockWebSocket {
		static OPEN = 1;
		static CLOSED = 3;
		readyState = MockWebSocket.OPEN;
		url: string;
		onopen: (() => void) | null = null;
		onmessage: ((event: { data: string }) => void) | null = null;
		onerror: ((err: unknown) => void) | null = null;
		onclose: ((event: { code: number; reason?: string }) => void) | null = null;
		sent: string[] = [];

		constructor(url: string) {
			this.url = url;
			mockWsInstances.push(this);
			setTimeout(() => {
				this.onopen?.();
			}, 0);
		}

		send(data: string) {
			this.sent.push(data);
		}

		close(code = 1000) {
			this.readyState = MockWebSocket.CLOSED;
			this.onclose?.({ code });
		}
	}

	beforeEach(() => {
		vi.useFakeTimers();
		mockWsInstances = [];
		vi.stubGlobal('WebSocket', MockWebSocket);
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.restoreAllMocks();
	});

	function makeCallbacks(overrides: Partial<SyncPlayControllerCallbacks> = {}): SyncPlayControllerCallbacks {
		return {
			getVideoElement: () => null,
			getLocalCurrentTime: () => 10,
			getIsPaused: () => false,
			onRemotePlay: vi.fn(),
			onRemotePause: vi.fn(),
			onRemoteSeek: vi.fn(),
			onRemoteContentChange: vi.fn(),
			onRoomStateChange: vi.fn(),
			...overrides,
		};
	}

	const sampleRoom: SyncPlayRoom = {
		room_code: 'ROOM1',
		created_at: 1000,
		host_session_id: 'host-1',
		content: { type: 'channel', id: '4.1', title: 'NBC' },
		playback_state: { is_playing: true, position: 10, playback_rate: 1.0, updated_at: 1000 },
		participants: [
			{
				session_id: 'host-1',
				user_name: 'Alice',
				is_host: true,
				is_ready: true,
				ping_ms: 10,
				position: 10,
				last_seen: 1000,
			},
		],
	};

	it('connects to websocket and transitions status to connected upon room_state message', async () => {
		const callbacks = makeCallbacks();
		const controller = createSyncPlayController(callbacks);

		const joinPromise = controller.joinRoom('ROOM1', 'Bob');
		await vi.advanceTimersByTimeAsync(1);

		expect(mockWsInstances.length).toBe(1);
		const ws = mockWsInstances[0];

		ws.onmessage?.({
			data: JSON.stringify({
				type: 'room_state',
				room: sampleRoom,
				your_session_id: 'user-2',
			}),
		});

		await joinPromise;

		expect(controller.getStatus()).toBe('connected');
		expect(controller.getRoomCode()).toBe('ROOM1');
		expect(controller.getSessionId()).toBe('user-2');
		expect(controller.getIsHost()).toBe(false);
		expect(callbacks.onRoomStateChange).toHaveBeenCalledWith(sampleRoom);

		controller.destroy();
	});

	it('automatically reconnects with backoff when WebSocket drops mid-session', async () => {
		const callbacks = makeCallbacks();
		const controller = createSyncPlayController(callbacks);

		const joinPromise = controller.joinRoom('ROOM1', 'Bob');
		await vi.advanceTimersByTimeAsync(1);

		const ws1 = mockWsInstances[0];
		ws1.onmessage?.({
			data: JSON.stringify({
				type: 'room_state',
				room: sampleRoom,
				your_session_id: 'user-2',
			}),
		});
		await joinPromise;
		expect(controller.getStatus()).toBe('connected');

		// Drop socket abnormally (e.g. 1006 abnormal closure)
		ws1.close(1006);
		expect(controller.getStatus()).toBe('disconnected');

		// First reconnect attempt after 1000ms backoff
		expect(mockWsInstances.length).toBe(1);
		await vi.advanceTimersByTimeAsync(1050);

		expect(mockWsInstances.length).toBe(2);
		const ws2 = mockWsInstances[1];
		expect(ws2.url).toContain('ROOM1');

		// Connect success
		ws2.onmessage?.({
			data: JSON.stringify({
				type: 'room_state',
				room: sampleRoom,
				your_session_id: 'user-2',
			}),
		});

		expect(controller.getStatus()).toBe('connected');

		controller.destroy();
	});

	it('does not reconnect when close code is 4004 (room ended)', async () => {
		const callbacks = makeCallbacks();
		const controller = createSyncPlayController(callbacks);

		const joinPromise = controller.joinRoom('ROOM1', 'Bob');
		await vi.advanceTimersByTimeAsync(1);

		const ws1 = mockWsInstances[0];
		ws1.onmessage?.({
			data: JSON.stringify({
				type: 'room_state',
				room: sampleRoom,
				your_session_id: 'user-2',
			}),
		});
		await joinPromise;

		// Server reaped room
		ws1.close(4004);
		expect(controller.getStatus()).toBe('ended');

		// Wait 10 seconds, no new socket should be opened
		await vi.advanceTimersByTimeAsync(10000);
		expect(mockWsInstances.length).toBe(1);

		controller.destroy();
	});

	it('cancels reconnect when leaveRoom() is called', async () => {
		const callbacks = makeCallbacks();
		const controller = createSyncPlayController(callbacks);

		const joinPromise = controller.joinRoom('ROOM1', 'Bob');
		await vi.advanceTimersByTimeAsync(1);

		const ws1 = mockWsInstances[0];
		ws1.onmessage?.({
			data: JSON.stringify({
				type: 'room_state',
				room: sampleRoom,
				your_session_id: 'user-2',
			}),
		});
		await joinPromise;

		// Drop connection
		ws1.close(1006);

		// Before reconnect timer fires, user intentionally leaves
		controller.leaveRoom();

		// Advance time
		await vi.advanceTimersByTimeAsync(10000);
		expect(mockWsInstances.length).toBe(1);
		expect(controller.getStatus()).toBe('disconnected');
	});

	it('cancels reconnect and timers when destroy() is called', async () => {
		const callbacks = makeCallbacks();
		const controller = createSyncPlayController(callbacks);

		const joinPromise = controller.joinRoom('ROOM1', 'Bob');
		await vi.advanceTimersByTimeAsync(1);

		const ws1 = mockWsInstances[0];
		ws1.onmessage?.({
			data: JSON.stringify({
				type: 'room_state',
				room: sampleRoom,
				your_session_id: 'user-2',
			}),
		});
		await joinPromise;

		ws1.close(1006);
		controller.destroy();

		await vi.advanceTimersByTimeAsync(10000);
		expect(mockWsInstances.length).toBe(1);
	});
});
