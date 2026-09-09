import { api, type SyncPlayContent, type SyncPlayParticipant, type SyncPlayRoom } from '$lib/api';
import { logger } from '$lib/logger';

export type SyncPlayStatus = 'disconnected' | 'connecting' | 'connected' | 'in_sync' | 'syncing' | 'ended';

export interface SyncPlayControllerCallbacks {
	getVideoElement: () => HTMLVideoElement | null;
	getLocalCurrentTime: () => number;
	getIsPaused: () => boolean;
	onRemotePlay: (position: number, playbackRate: number) => void;
	onRemotePause: (position: number) => void;
	onRemoteSeek: (position: number) => void;
	onRemoteContentChange: (content: SyncPlayContent) => void;
	onRoomStateChange?: (room: SyncPlayRoom | null) => void;
}

export interface SyncPlayController {
	getStatus: () => SyncPlayStatus;
	getRoom: () => SyncPlayRoom | null;
	getRoomCode: () => string | null;
	getIsHost: () => boolean;
	getParticipants: () => SyncPlayParticipant[];
	getPingMs: () => number;
	getSessionId: () => string | null;
	createRoom: (content: SyncPlayContent, userName?: string) => Promise<string>;
	joinRoom: (roomCode: string, userName?: string) => Promise<void>;
	leaveRoom: () => void;
	sendPlay: (position: number, playbackRate?: number) => void;
	sendPause: (position: number) => void;
	sendSeek: (position: number) => void;
	sendProgress: (position: number, isReady?: boolean) => void;
	changeContent: (content: SyncPlayContent) => void;
	transferHost: (targetSessionId: string) => void;
	checkAndApplyDrift: () => { drift: number; appliedRate: number; didSeek: boolean };
	destroy: () => void;
}

const PING_INTERVAL_MS = 4000;
const PROGRESS_INTERVAL_MS = 2000;
const DRIFT_TOLERANCE_SECONDS = 0.25;
const DRIFT_MAX_MICRO_SECONDS = 2.0;

export function createSyncPlayController(callbacks: SyncPlayControllerCallbacks): SyncPlayController {
	let status: SyncPlayStatus = 'disconnected';
	let room: SyncPlayRoom | null = null;
	let sessionId: string | null = null;
	let isHost = false;
	let pingMs = 0;
	let ws: WebSocket | null = null;
	let pingTimer: ReturnType<typeof setInterval> | undefined;
	let progressTimer: ReturnType<typeof setInterval> | undefined;
	let isApplyingRemoteAction = false;
	let destroyed = false;
	let currentRoomCode: string | null = null;
	let currentUserName: string | undefined = undefined;
	let reconnectAttempt = 0;
	let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
	let isIntentionalDisconnect = false;
	const MAX_RECONNECT_ATTEMPTS = 5;

	function stopReconnect() {
		if (reconnectTimer !== undefined) {
			clearTimeout(reconnectTimer);
			reconnectTimer = undefined;
		}
		reconnectAttempt = 0;
	}

	function scheduleReconnect() {
		if (destroyed || isIntentionalDisconnect || !currentRoomCode) return;
		if (reconnectAttempt >= MAX_RECONNECT_ATTEMPTS) {
			logger.warn(`SyncPlay reconnect failed after ${MAX_RECONNECT_ATTEMPTS} attempts`);
			return;
		}
		const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), 16000);
		reconnectAttempt++;
		logger.info(`SyncPlay scheduling reconnect attempt ${reconnectAttempt} in ${delay}ms`);
		reconnectTimer = setTimeout(() => {
			reconnectTimer = undefined;
			if (destroyed || isIntentionalDisconnect || !currentRoomCode) return;
			connectWebSocket(currentRoomCode, currentUserName).catch((err) => {
				logger.warn('SyncPlay reconnect attempt failed', err);
			});
		}, delay);
	}

	function getAuthoritativePosition(): number {
		if (!room) return 0;
		if (!room.playback_state.is_playing) return room.playback_state.position;
		const now = Date.now() / 1000;
		const elapsed = (now - room.playback_state.updated_at) * (room.playback_state.playback_rate || 1.0);
		return Math.max(0, room.playback_state.position + elapsed);
	}

	function sendJson(msg: Record<string, unknown>) {
		if (ws && ws.readyState === WebSocket.OPEN) {
			ws.send(JSON.stringify(msg));
		}
	}

	function startTimers() {
		stopTimers();
		pingTimer = setInterval(() => {
			if (ws && ws.readyState === WebSocket.OPEN) {
				sendJson({
					type: 'ping',
					client_time: performance.now(),
				});
			}
		}, PING_INTERVAL_MS);

		progressTimer = setInterval(() => {
			if (ws && ws.readyState === WebSocket.OPEN) {
				const video = callbacks.getVideoElement();
				const isReady = video ? video.readyState >= 3 : true;
				sendJson({
					type: 'progress',
					position: callbacks.getLocalCurrentTime(),
					is_ready: isReady,
					ping_ms: pingMs,
				});
			}
		}, PROGRESS_INTERVAL_MS);
	}

	function stopTimers() {
		if (pingTimer) {
			clearInterval(pingTimer);
			pingTimer = undefined;
		}
		if (progressTimer) {
			clearInterval(progressTimer);
			progressTimer = undefined;
		}
	}

	function connectWebSocket(roomCode: string, userName?: string): Promise<void> {
		currentRoomCode = roomCode;
		currentUserName = userName;
		isIntentionalDisconnect = false;

		return new Promise((resolve, reject) => {
			if (ws) {
				ws.close();
				ws = null;
			}

			status = 'connecting';
			const wsUrl = api.syncPlayWsUrl(roomCode, undefined, userName);

			try {
				ws = new WebSocket(wsUrl);
			} catch (err) {
				status = 'disconnected';
				reject(err);
				return;
			}

			let resolved = false;

			ws.onopen = () => {
				status = 'connected';
				reconnectAttempt = 0;
				startTimers();
			};

			ws.onmessage = (event) => {
				try {
					const data = JSON.parse(event.data);
					handleServerMessage(data);
					if (!resolved && data.type === 'room_state') {
						resolved = true;
						resolve();
					}
				} catch (e) {
					logger.error('Failed to parse SyncPlay WebSocket message', e);
				}
			};

			ws.onerror = (err) => {
				logger.error('SyncPlay WebSocket error', err);
				if (!resolved) {
					resolved = true;
					reject(new Error('WebSocket connection failed'));
				}
			};

			ws.onclose = (event: CloseEvent) => {
				stopTimers();
				if (event.code === 4004) {
					status = 'ended';
					stopReconnect();
				} else if (isIntentionalDisconnect || destroyed) {
					status = 'disconnected';
					stopReconnect();
				} else {
					status = 'disconnected';
					scheduleReconnect();
				}
				if (!resolved) {
					resolved = true;
					reject(new Error('WebSocket closed'));
				}
			};
		});
	}

	function handleServerMessage(data: Record<string, unknown>) {
		const type = data.type as string;

		switch (type) {
			case 'room_state': {
				room = data.room as SyncPlayRoom;
				sessionId = data.your_session_id as string;
				isHost = room.host_session_id === sessionId;
				status = 'connected';
				callbacks.onRoomStateChange?.(room);
				break;
			}

			case 'participant_joined': {
				if (room) {
					const participant = data.participant as SyncPlayParticipant;
					const exists = room.participants.some((p) => p.session_id === participant.session_id);
					if (!exists) {
						room.participants = [...room.participants, participant];
					}
					callbacks.onRoomStateChange?.(room);
				}
				break;
			}

			case 'participant_left': {
				if (room) {
					const leftSessionId = data.session_id as string;
					const newHostSessionId = data.new_host_session_id as string | null;
					room.participants = room.participants.filter((p) => p.session_id !== leftSessionId);
					if (newHostSessionId) {
						room.host_session_id = newHostSessionId;
						for (const p of room.participants) {
							p.is_host = p.session_id === newHostSessionId;
						}
					}
					isHost = room.host_session_id === sessionId;
					callbacks.onRoomStateChange?.(room);
				}
				break;
			}

			case 'participant_updated': {
				if (room) {
					const updated = data.participant as SyncPlayParticipant;
					room.participants = room.participants.map((p) =>
						p.session_id === updated.session_id ? updated : p,
					);
					callbacks.onRoomStateChange?.(room);
				}
				break;
			}

			case 'playback_update': {
				if (room) {
					const action = data.action as 'play' | 'pause' | 'seek';
					const position = Number(data.position ?? 0);
					const rate = Number(data.playback_rate ?? 1.0);
					const isPlaying = Boolean(data.is_playing);
					const serverTime = Number(data.server_time ?? Date.now() / 1000);
					const triggeredBy = data.triggered_by as string | undefined;

					room.playback_state = {
						is_playing: isPlaying,
						position,
						playback_rate: rate,
						updated_at: serverTime,
					};

					callbacks.onRoomStateChange?.(room);

					// If triggered by another participant, apply to local player
					if (triggeredBy !== sessionId) {
						isApplyingRemoteAction = true;
						try {
							if (action === 'play') {
								callbacks.onRemotePlay(position, rate);
							} else if (action === 'pause') {
								callbacks.onRemotePause(position);
							} else if (action === 'seek') {
								callbacks.onRemoteSeek(position);
							}
						} finally {
							setTimeout(() => {
								isApplyingRemoteAction = false;
							}, 200);
						}
					}
				}
				break;
			}

			case 'content_changed': {
				if (room) {
					const newContent = data.content as SyncPlayContent;
					room.content = newContent;
					if (data.room) {
						room = data.room as SyncPlayRoom;
					}
					callbacks.onRoomStateChange?.(room);
					callbacks.onRemoteContentChange(newContent);
				}
				break;
			}

			case 'host_changed': {
				if (room) {
					const newHostId = data.new_host_session_id as string;
					room.host_session_id = newHostId;
					for (const p of room.participants) {
						p.is_host = p.session_id === newHostId;
					}
					isHost = room.host_session_id === sessionId;
					callbacks.onRoomStateChange?.(room);
				}
				break;
			}

			case 'pong': {
				const clientTime = Number(data.client_time ?? 0);
				const rtt = performance.now() - clientTime;
				pingMs = Math.max(1, Math.round(rtt));
				break;
			}
		}
	}

	return {
		getStatus: () => status,
		getRoom: () => room,
		getRoomCode: () => room?.room_code ?? null,
		getIsHost: () => isHost,
		getParticipants: () => room?.participants ?? [],
		getPingMs: () => pingMs,
		getSessionId: () => sessionId,

		createRoom: async (content: SyncPlayContent, userName?: string) => {
			const res = await api.createSyncPlayRoom(content, userName);
			await connectWebSocket(res.room_code, userName);
			return res.room_code;
		},

		joinRoom: async (roomCode: string, userName?: string) => {
			await connectWebSocket(roomCode.trim().toUpperCase(), userName);
		},

		leaveRoom: () => {
			isIntentionalDisconnect = true;
			stopReconnect();
			currentRoomCode = null;
			if (ws && ws.readyState === WebSocket.OPEN) {
				sendJson({ type: 'leave' });
				ws.close();
			}
			ws = null;
			room = null;
			sessionId = null;
			isHost = false;
			status = 'disconnected';
			stopTimers();
			callbacks.onRoomStateChange?.(null);
		},

		sendPlay: (position: number, playbackRate = 1.0) => {
			if (isApplyingRemoteAction) return;
			sendJson({
				type: 'play',
				position,
				playback_rate: playbackRate,
			});
		},

		sendPause: (position: number) => {
			if (isApplyingRemoteAction) return;
			sendJson({
				type: 'pause',
				position,
			});
		},

		sendSeek: (position: number) => {
			if (isApplyingRemoteAction) return;
			sendJson({
				type: 'seek',
				position,
			});
		},

		sendProgress: (position: number, isReady = true) => {
			sendJson({
				type: 'progress',
				position,
				is_ready: isReady,
				ping_ms: pingMs,
			});
		},

		changeContent: (content: SyncPlayContent) => {
			sendJson({
				type: 'change_content',
				content,
			});
		},

		transferHost: (targetSessionId: string) => {
			sendJson({
				type: 'transfer_host',
				target_session_id: targetSessionId,
			});
		},

		checkAndApplyDrift: () => {
			if (!room || !room.playback_state.is_playing || isApplyingRemoteAction || status === 'disconnected') {
				return { drift: 0, appliedRate: 1.0, didSeek: false };
			}

			const video = callbacks.getVideoElement();
			if (!video || video.paused) {
				return { drift: 0, appliedRate: 1.0, didSeek: false };
			}

			const localPos = callbacks.getLocalCurrentTime();
			const authPos = getAuthoritativePosition();
			const drift = localPos - authPos;

			let appliedRate: number;
			let didSeek = false;

			if (Math.abs(drift) > DRIFT_MAX_MICRO_SECONDS) {
				// Hard seek to authoritative position
				video.currentTime = authPos;
				video.playbackRate = 1.0;
				appliedRate = 1.0;
				didSeek = true;
				status = 'syncing';
			} else if (Math.abs(drift) > DRIFT_TOLERANCE_SECONDS) {
				// Micro-speed adjustment: local is behind -> speed up to 1.05; local is ahead -> slow to 0.95
				appliedRate = drift < 0 ? 1.05 : 0.95;
				video.playbackRate = appliedRate;
				status = 'syncing';
			} else {
				// In sync
				if (video.playbackRate !== 1.0) {
					video.playbackRate = 1.0;
				}
				appliedRate = 1.0;
				status = 'in_sync';
			}

			return { drift, appliedRate, didSeek };
		},

		destroy: () => {
			if (destroyed) return;
			destroyed = true;
			isIntentionalDisconnect = true;
			stopReconnect();
			currentRoomCode = null;
			stopTimers();
			if (ws) {
				ws.close();
				ws = null;
			}
		},
	};
}
