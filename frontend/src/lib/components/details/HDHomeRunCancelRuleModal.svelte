<script lang="ts">
	import { _ } from 'svelte-i18n';

	interface Props {
		title: string;
		onConfirm: () => void;
		onClose: () => void;
	}

	let { title, onConfirm, onClose }: Props = $props();

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="confirm-backdrop" onclick={onClose} role="presentation"></div>
<div
	class="confirm-dialog"
	role="alertdialog"
	aria-modal="true"
	aria-labelledby="cancel-confirm-title"
	aria-describedby="cancel-confirm-desc"
>
	<h3 id="cancel-confirm-title" class="confirm-title">
		{$_('hdhomerun.detail.cancel_recording_confirm_title')}
	</h3>
	<p id="cancel-confirm-desc" class="confirm-message">
		{$_('hdhomerun.detail.cancel_recording_confirm_message', { values: { title } })}
	</p>
	<div class="confirm-actions">
		<button type="button" class="btn btn-secondary" onclick={onClose}>
			{$_('hdhomerun.detail.keep_recording')}
		</button>
		<button type="button" class="btn btn-danger" onclick={onConfirm}>
			{$_('hdhomerun.detail.cancel_recording')}
		</button>
	</div>
</div>

<style>
	.confirm-backdrop {
		position: fixed;
		inset: 0;
		z-index: 90;
		background: rgba(0, 0, 0, 0.65);
		backdrop-filter: blur(4px);
	}

	.confirm-dialog {
		position: fixed;
		z-index: 91;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: min(28rem, calc(100vw - 2rem));
		background: var(--color-surface, #1e2126);
		border: 1px solid var(--color-border, #2f333b);
		border-radius: 0.75rem;
		padding: 1.25rem;
		box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
	}

	.confirm-title {
		margin: 0;
		font-size: 1.15rem;
		font-weight: 700;
		color: var(--color-text, #f2f3f5);
	}

	.confirm-message {
		margin: 0;
		font-size: 0.9rem;
		line-height: 1.45;
		color: var(--color-text-muted, #9aa0aa);
	}

	.confirm-actions {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 0.6rem;
		margin-top: 0.5rem;
	}

	.btn {
		font-size: 0.85rem;
		font-weight: 600;
		padding: 0.45rem 0.9rem;
		border-radius: 0.45rem;
		cursor: pointer;
		border: 1px solid transparent;
		transition: opacity 0.15s ease;
	}

	.btn:hover {
		opacity: 0.9;
	}

	.btn-secondary {
		background: var(--color-bg, #14161a);
		border-color: var(--color-border, #2f333b);
		color: var(--color-text, #f2f3f5);
	}

	.btn-danger {
		background: var(--color-error, #e05a5a);
		color: #fff;
	}
</style>
