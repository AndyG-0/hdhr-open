<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { SyncPlayContent, SyncPlayParticipant, SyncPlayRoom } from '$lib/api';
	import type { SyncPlayStatus } from '$lib/syncplay-controller';
	import PlayerIcon from './icons/PlayerIcon.svelte';

	interface Props {
		show?: boolean;
		room: SyncPlayRoom | null;
		roomCode: string | null;
		participants?: SyncPlayParticipant[];
		isHost?: boolean;
		pingMs?: number;
		status?: SyncPlayStatus;
		currentContent?: SyncPlayContent | null;
		onJoinRoom: (code: string) => Promise<void> | void;
		onCreateRoom: () => Promise<void> | void;
		onLeaveRoom: () => void;
		onTransferHost?: (targetSessionId: string) => void;
		onClose: () => void;
	}

	let {
		show = true,
		room = null,
		roomCode = null,
		participants = [],
		isHost = false,
		pingMs = 0,
		status = 'disconnected',
		currentContent = null,
		onJoinRoom,
		onCreateRoom,
		onLeaveRoom,
		onTransferHost,
		onClose,
	}: Props = $props();

	let inputCode = $state('');
	let copied = $state(false);
	let isJoining = $state(false);
	let isCreating = $state(false);
	let errorMessage = $state<string | null>(null);

	async function handleJoin() {
		const cleanCode = inputCode.trim().toUpperCase();
		if (cleanCode.length < 4) return;
		isJoining = true;
		errorMessage = null;
		try {
			await onJoinRoom(cleanCode);
			inputCode = '';
		} catch (err: any) {
			errorMessage = err?.message || 'Failed to join room';
		} finally {
			isJoining = false;
		}
	}

	async function handleCreate() {
		isCreating = true;
		errorMessage = null;
		try {
			await onCreateRoom();
		} catch (err: any) {
			errorMessage = err?.message || 'Failed to create room';
		} finally {
			isCreating = false;
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
			// ignore clipboard write failure
		}
	}
</script>

{#if show}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="syncplay-modal-overlay"
		data-testid="syncplay-modal"
		onclick={(e) => e.target === e.currentTarget && onClose()}
	>
		<div
			class="syncplay-modal-card"
			role="dialog"
			aria-modal="true"
			aria-labelledby="syncplay-title"
			tabindex="-1"
			onclick={(e) => e.stopPropagation()}
		>
			<div class="modal-header">
				<div class="header-title" id="syncplay-title">
					<PlayerIcon name="syncplay" size={22} />
					<span>{$_('syncplay.title', { default: 'SyncPlay Watch Party' })}</span>
				</div>
				<button
					type="button"
					class="close-btn"
					onclick={onClose}
					aria-label={$_('player.close', { default: 'Close' })}
				>
					&times;
				</button>
			</div>

			<div class="modal-body">
				{#if errorMessage}
					<div class="error-banner">
						{errorMessage}
					</div>
				{/if}

				{#if roomCode}
					<!-- Active Room View -->
					<div class="active-room-section">
						<div class="room-code-badge">
							<div class="code-info">
								<span class="label">{$_('syncplay.room_code', { default: 'Room Code' })}</span>
								<span class="code">{roomCode}</span>
							</div>
							<button type="button" class="copy-btn" onclick={copyRoomCode}>
								{copied ? $_('syncplay.copied', { default: 'Copied!' }) : $_('syncplay.copy_code', { default: 'Copy Code' })}
							</button>
						</div>

						{#if room?.content}
							<div class="content-banner">
								<span class="content-label">{$_('syncplay.watching', { default: 'Watching' })}:</span>
								<span class="content-title">{room.content.title || room.content.id}</span>
								{#if room.content.channel_number}
									<span class="channel-pill">{room.content.channel_number}</span>
								{/if}
							</div>
						{/if}

						<div class="roster-heading">
							<span>{$_('syncplay.participants', { default: 'Participants' })} ({participants.length})</span>
							<span class="status-indicator" class:connected={status === 'connected' || status === 'in_sync'}>
								{#if status === 'in_sync'}
									{$_('syncplay.synced', { default: 'Synced' })}
								{:else if status === 'syncing'}
									{$_('syncplay.syncing', { default: 'Syncing…' })}
								{:else if status === 'ended'}
									{$_('syncplay.session_ended', { default: 'Session ended — please rejoin' })}
								{:else}
									{$_('syncplay.connected', { default: 'Connected' })}
								{/if}
							</span>
						</div>

						<div class="participants-list">
							{#each participants as user (user.session_id)}
								<div class="participant-row">
									<div class="user-info">
										<span class="user-avatar">{user.user_name.charAt(0).toUpperCase()}</span>
										<span class="user-name">{user.user_name}</span>
										{#if user.is_host}
											<span class="host-badge">{$_('syncplay.host', { default: 'Host' })}</span>
										{/if}
									</div>
									<div class="user-status">
										{#if user.ping_ms > 0}
											<span class="ping-badge">{Math.round(user.ping_ms)}ms</span>
										{/if}
										<span class="ready-badge" class:ready={user.is_ready}>
											{user.is_ready ? $_('syncplay.ready', { default: 'Ready' }) : $_('syncplay.buffering', { default: 'Buffering' })}
										</span>
										{#if isHost && !user.is_host && onTransferHost}
											<button
												type="button"
												class="make-host-btn"
												onclick={() => onTransferHost(user.session_id)}
												title={$_('syncplay.make_host', { default: 'Transfer Host' })}
											>
												{$_('syncplay.make_host', { default: 'Make Host' })}
											</button>
										{/if}
									</div>
								</div>
							{/each}
						</div>

						<div class="actions-row">
							<button type="button" class="leave-btn" onclick={onLeaveRoom}>
								{$_('syncplay.leave', { default: 'Leave Room' })}
							</button>
						</div>
					</div>
				{:else}
					<!-- Create or Join View -->
					<div class="join-create-section">
						<p class="description">
							{$_('syncplay.description', {
								default: 'Watch Live TV and DVR recordings in real-time synchronization with family and friends across Web, Apple TV, iOS, and Android.',
							})}
						</p>

						<div class="join-box">
							<label for="room-code-input" class="input-label">
								{$_('syncplay.join_with_code', { default: 'Join with Room Code' })}
							</label>
							<div class="input-row">
								<input
									id="room-code-input"
									type="text"
									placeholder={$_('syncplay.code_placeholder', { default: 'Enter 6-digit code' })}
									maxlength="10"
									bind:value={inputCode}
									onkeydown={(e) => e.key === 'Enter' && handleJoin()}
								/>
								<button
									type="button"
									class="join-btn"
									disabled={inputCode.trim().length < 4 || isJoining}
									onclick={handleJoin}
								>
									{isJoining ? $_('syncplay.joining', { default: 'Joining…' }) : $_('syncplay.join', { default: 'Join' })}
								</button>
							</div>
						</div>

						<div class="divider">
							<span>{$_('syncplay.or', { default: 'OR' })}</span>
						</div>

						<button type="button" class="create-btn" disabled={isCreating} onclick={handleCreate}>
							{isCreating ? $_('syncplay.creating', { default: 'Creating…' }) : $_('syncplay.create_new', { default: 'Create New Watch Room' })}
						</button>
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.syncplay-modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 9999;
		background: rgba(0, 0, 0, 0.78);
		backdrop-filter: blur(8px);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		pointer-events: auto;
	}

	.syncplay-modal-card {
		background: rgba(26, 26, 32, 0.98);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.85rem;
		width: 100%;
		max-width: 28rem;
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
		font-size: 1.25rem;
		cursor: pointer;
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
	}

	.close-btn:hover {
		color: #ffffff;
		background: rgba(255, 255, 255, 0.1);
	}

	.modal-body {
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.error-banner {
		background: rgba(239, 68, 68, 0.2);
		border: 1px solid rgba(239, 68, 68, 0.4);
		color: #fca5a5;
		padding: 0.5rem 0.75rem;
		border-radius: 0.4rem;
		font-size: 0.85rem;
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

	.create-btn:hover:not(:disabled) {
		background: rgba(255, 255, 255, 0.22);
		border-color: rgba(255, 255, 255, 0.4);
	}

	.create-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
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

	.code-info {
		display: flex;
		flex-direction: column;
	}

	.room-code-badge .label {
		font-size: 0.75rem;
		color: rgba(255, 255, 255, 0.7);
	}

	.room-code-badge .code {
		font-family: ui-monospace, SFMono-Regular, monospace;
		font-size: 1.25rem;
		font-weight: 700;
		color: #38bdf8;
		letter-spacing: 0.1em;
	}

	.copy-btn {
		background: rgba(255, 255, 255, 0.15);
		border: none;
		color: #ffffff;
		font-size: 0.8rem;
		padding: 0.35rem 0.65rem;
		border-radius: 0.3rem;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.copy-btn:hover {
		background: rgba(255, 255, 255, 0.25);
	}

	.content-banner {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.85rem;
		background: rgba(0, 0, 0, 0.3);
		padding: 0.4rem 0.6rem;
		border-radius: 0.35rem;
	}

	.content-label {
		color: rgba(255, 255, 255, 0.6);
	}

	.content-title {
		font-weight: 600;
		color: #ffffff;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.channel-pill {
		background: rgba(56, 189, 248, 0.25);
		color: #38bdf8;
		padding: 0.05rem 0.3rem;
		border-radius: 0.2rem;
		font-size: 0.75rem;
		font-weight: 600;
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
		margin-top: 0.25rem;
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
		max-height: 12rem;
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

	.make-host-btn {
		background: rgba(255, 255, 255, 0.1);
		border: 1px solid rgba(255, 255, 255, 0.2);
		color: #ffffff;
		font-size: 0.65rem;
		padding: 0.1rem 0.35rem;
		border-radius: 0.2rem;
		cursor: pointer;
	}

	.make-host-btn:hover {
		background: rgba(255, 255, 255, 0.2);
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
