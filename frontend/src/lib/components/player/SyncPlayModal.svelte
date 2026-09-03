<script lang="ts">
	import { _ } from 'svelte-i18n';
	import PlayerIcon from './icons/PlayerIcon.svelte';

	interface Participant {
		id: string;
		name: string;
		isReady: boolean;
		pingMs: number;
		isHost: boolean;
	}

	interface Props {
		isOpen: boolean;
		roomCode?: string | null;
		participants?: Participant[];
		isConnected?: boolean;
		onJoinRoom?: (code: string) => void;
		onCreateRoom?: () => void;
		onLeaveRoom?: () => void;
		onClose: () => void;
	}

	let {
		isOpen = false,
		roomCode = null,
		participants = [],
		isConnected = false,
		onJoinRoom = () => {},
		onCreateRoom = () => {},
		onLeaveRoom = () => {},
		onClose,
	}: Props = $props();

	let inputCode = $state('');
	let copied = $state(false);

	function handleJoin() {
		if (inputCode.trim().length >= 4) {
			onJoinRoom(inputCode.trim().toUpperCase());
			inputCode = '';
		}
	}

	async function copyRoomCode() {
		if (!roomCode) return;
		try {
			await navigator.clipboard.writeText(roomCode);
			copied = true;
			setTimeout(() => {
				copied = false;
			}, 2000);
		} catch {
			// ignore
		}
	}
</script>

{#if isOpen}
	<div class="syncplay-modal-overlay" role="dialog" aria-modal="true" aria-label="SyncPlay Watch Party">
		<div class="syncplay-modal-card">
			<div class="modal-header">
				<div class="header-title">
					<PlayerIcon name="syncplay" size={24} />
					<span>SyncPlay Watch Party</span>
				</div>
				<button type="button" class="close-btn" onclick={onClose} aria-label="Close">✕</button>
			</div>

			<div class="modal-body">
				{#if roomCode}
					<!-- Active Room View -->
					<div class="active-room-section">
						<div class="room-code-badge">
							<span class="label">Room Code:</span>
							<span class="code">{roomCode}</span>
							<button type="button" class="copy-btn" onclick={copyRoomCode}>
								{copied ? '✓ Copied' : 'Copy'}
							</button>
						</div>

						<div class="roster-heading">
							<span>Participants ({participants.length || 1})</span>
							<span class="status-indicator" class:connected={isConnected}>
								{isConnected ? 'In Sync' : 'Connecting…'}
							</span>
						</div>

						<div class="participants-list">
							{#if participants.length > 0}
								{#each participants as user (user.id)}
									<div class="participant-row">
										<div class="user-info">
											<span class="user-avatar">{user.name.charAt(0).toUpperCase()}</span>
											<span class="user-name">{user.name}</span>
											{#if user.isHost}
												<span class="host-badge">Host</span>
											{/if}
										</div>
										<div class="user-status">
											<span class="ping-badge">{user.pingMs}ms</span>
											<span class="ready-badge" class:ready={user.isReady}>
												{user.isReady ? 'Ready' : 'Buffering'}
											</span>
										</div>
									</div>
								{/each}
							{:else}
								<div class="participant-row">
									<div class="user-info">
										<span class="user-avatar">Y</span>
										<span class="user-name">You (Host)</span>
										<span class="host-badge">Host</span>
									</div>
									<div class="user-status">
										<span class="ready-badge ready">Ready</span>
									</div>
								</div>
							{/if}
						</div>

						<div class="actions-row">
							<button type="button" class="leave-btn" onclick={onLeaveRoom}>
								Leave Room
							</button>
						</div>
					</div>
				{:else}
					<!-- Create or Join View -->
					<div class="join-create-section">
						<p class="description">
							Watch Live TV and DVR recordings in real-time synchronization with family and friends across Web, Apple TV, iOS, and Android.
						</p>

						<div class="join-box">
							<label for="room-code-input" class="input-label">Join with Room Code</label>
							<div class="input-row">
								<input
									id="room-code-input"
									type="text"
									placeholder="Enter 6-digit code"
									maxlength="10"
									bind:value={inputCode}
									onkeydown={(e) => e.key === 'Enter' && handleJoin()}
								/>
								<button
									type="button"
									class="join-btn"
									disabled={inputCode.trim().length < 4}
									onclick={handleJoin}
								>
									Join
								</button>
							</div>
						</div>

						<div class="divider">
							<span>OR</span>
						</div>

						<button type="button" class="create-btn" onclick={onCreateRoom}>
							Create New Watch Room
						</button>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.syncplay-modal-overlay {
		position: absolute;
		inset: 0;
		z-index: 200;
		background: rgba(0, 0, 0, 0.75);
		backdrop-filter: blur(8px);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
	}

	.syncplay-modal-card {
		background: rgba(26, 26, 32, 0.98);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.85rem;
		width: 100%;
		max-width: 26rem;
		box-shadow: 0 16px 48px rgba(0, 0, 0, 0.85);
		color: #ffffff;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		animation: modal-pop 0.15s ease;
	}

	@keyframes modal-pop {
		from { opacity: 0; transform: scale(0.95); }
		to { opacity: 1; transform: scale(1); }
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
	}

	.header-title {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.1rem;
		font-weight: 600;
	}

	.close-btn {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.6);
		font-size: 1.1rem;
		cursor: pointer;
		padding: 0.25rem;
	}

	.close-btn:hover {
		color: #ffffff;
	}

	.modal-body {
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.description {
		font-size: 0.85rem;
		color: rgba(255, 255, 255, 0.75);
		line-height: 1.4;
		margin: 0 0 0.5rem;
	}

	.join-box {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.input-label {
		font-size: 0.8rem;
		font-weight: 600;
		color: rgba(255, 255, 255, 0.65);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.input-row {
		display: flex;
		gap: 0.5rem;
	}

	.input-row input {
		flex: 1;
		background: rgba(0, 0, 0, 0.4);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.4rem;
		padding: 0.5rem 0.75rem;
		color: #ffffff;
		font-size: 0.95rem;
		text-transform: uppercase;
		font-family: ui-monospace, SFMono-Regular, monospace;
		outline: none;
	}

	.input-row input:focus {
		border-color: #38bdf8;
		box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.25);
	}

	.join-btn {
		background: #38bdf8;
		border: none;
		color: #000000;
		font-weight: 600;
		padding: 0.5rem 1rem;
		border-radius: 0.4rem;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.join-btn:hover:not(:disabled) {
		background: #7dd3fc;
	}

	.join-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.divider {
		display: flex;
		align-items: center;
		text-align: center;
		color: rgba(255, 255, 255, 0.4);
		font-size: 0.75rem;
		font-weight: 600;
		margin: 0.25rem 0;
	}

	.divider::before,
	.divider::after {
		content: '';
		flex: 1;
		border-bottom: 1px solid rgba(255, 255, 255, 0.12);
	}

	.divider span {
		padding: 0 0.5rem;
	}

	.create-btn {
		background: rgba(255, 255, 255, 0.12);
		border: 1px solid rgba(255, 255, 255, 0.25);
		color: #ffffff;
		font-weight: 600;
		padding: 0.6rem;
		border-radius: 0.4rem;
		cursor: pointer;
		transition: background 0.15s ease, border-color 0.15s ease;
	}

	.create-btn:hover {
		background: rgba(255, 255, 255, 0.22);
		border-color: rgba(255, 255, 255, 0.4);
	}

	/* Active Room View */
	.room-code-badge {
		display: flex;
		align-items: center;
		justify-content: space-between;
		background: rgba(56, 189, 248, 0.12);
		border: 1px solid rgba(56, 189, 248, 0.35);
		border-radius: 0.5rem;
		padding: 0.6rem 0.85rem;
	}

	.room-code-badge .label {
		font-size: 0.8rem;
		color: rgba(255, 255, 255, 0.7);
	}

	.room-code-badge .code {
		font-family: ui-monospace, SFMono-Regular, monospace;
		font-size: 1.15rem;
		font-weight: 700;
		color: #38bdf8;
		letter-spacing: 0.1em;
	}

	.copy-btn {
		background: rgba(255, 255, 255, 0.15);
		border: none;
		color: #ffffff;
		font-size: 0.75rem;
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
		cursor: pointer;
	}

	.roster-heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
		font-size: 0.8rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: rgba(255, 255, 255, 0.55);
		margin-top: 0.5rem;
	}

	.status-indicator {
		font-size: 0.75rem;
		color: #eab308;
	}

	.status-indicator.connected {
		color: #4ade80;
	}

	.participants-list {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		max-height: 10rem;
		overflow-y: auto;
	}

	.participant-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		background: rgba(0, 0, 0, 0.25);
		padding: 0.4rem 0.6rem;
		border-radius: 0.35rem;
	}

	.user-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.user-avatar {
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		background: #38bdf8;
		color: #000000;
		font-size: 0.75rem;
		font-weight: 700;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.user-name {
		font-size: 0.85rem;
		font-weight: 500;
	}

	.host-badge {
		font-size: 0.65rem;
		background: rgba(56, 189, 248, 0.25);
		color: #38bdf8;
		padding: 0.05rem 0.3rem;
		border-radius: 0.2rem;
		font-weight: 600;
	}

	.user-status {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.ping-badge {
		font-size: 0.7rem;
		color: rgba(255, 255, 255, 0.45);
		font-family: ui-monospace, monospace;
	}

	.ready-badge {
		font-size: 0.7rem;
		padding: 0.1rem 0.35rem;
		border-radius: 0.2rem;
		background: rgba(234, 179, 8, 0.2);
		color: #eab308;
	}

	.ready-badge.ready {
		background: rgba(74, 222, 128, 0.2);
		color: #4ade80;
	}

	.actions-row {
		display: flex;
		justify-content: flex-end;
		margin-top: 0.5rem;
	}

	.leave-btn {
		background: rgba(239, 68, 68, 0.15);
		border: 1px solid rgba(239, 68, 68, 0.4);
		color: #fca5a5;
		font-size: 0.85rem;
		font-weight: 600;
		padding: 0.4rem 0.85rem;
		border-radius: 0.35rem;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.leave-btn:hover {
		background: rgba(239, 68, 68, 0.3);
		color: #ffffff;
	}
</style>
