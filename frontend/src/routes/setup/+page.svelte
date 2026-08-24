<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { user } from '$lib/stores/user';
	import { needsSetup } from '$lib/stores/setup';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';

	let name = $state('');
	let avatar = $state('');
	let pin = $state('');
	let error = $state<string | null>(null);
	let creating = $state(false);

	async function createAdmin() {
		if (!name.trim()) return;
		if (pin && !/^\d{4,8}$/.test(pin)) {
			error = get(_)('settings.profile.pin_invalid');
			return;
		}
		creating = true;
		error = null;
		try {
			const me = await api.createSetupAdmin(name.trim(), avatar.trim() || undefined, pin || undefined);
			user.set(me);
			needsSetup.set(false);
			goto('/');
		} catch {
			error = get(_)('setup.create_error');
		} finally {
			creating = false;
		}
	}
</script>

<div class="setup-page">
	<h1>{$_('setup.title')}</h1>
	<p class="hint">{$_('setup.intro')}</p>

	<div class="setup-form">
		<label>
			{$_('settings.profile.name_label')}
			<input type="text" bind:value={name} placeholder="Alice" maxlength="40" />
		</label>
		<label>
			{$_('settings.profile.avatar_label')}
			<input type="text" bind:value={avatar} placeholder="🐱" maxlength="8" />
		</label>
		<label>
			{$_('setup.pin_label')}
			<input
				type="password"
				inputmode="numeric"
				bind:value={pin}
				placeholder={$_('setup.pin_placeholder')}
				maxlength="8"
			/>
		</label>
		{#if error}
			<p class="hint error">{error}</p>
		{/if}
		<button class="confirm-button" onclick={createAdmin} disabled={creating || !name.trim()}>
			{creating ? $_('setup.creating') : $_('setup.create_account')}
		</button>
	</div>
</div>

<style>
	.setup-page {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 2rem;
		gap: 1rem;
		text-align: center;
	}

	h1 {
		margin: 0;
	}

	.hint {
		color: var(--color-text-muted);
		max-width: 24rem;
	}

	.hint.error {
		color: var(--color-error);
	}

	.setup-form {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		width: 18rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 1rem;
		padding: 1.5rem;
		margin-top: 1rem;
	}

	.setup-form label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		width: 100%;
		font-size: 0.9rem;
		color: var(--color-text-muted);
		text-align: left;
	}

	.setup-form input {
		font: inherit;
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-text);
	}

	.confirm-button {
		align-self: stretch;
		background: var(--color-accent);
		color: var(--color-surface);
		border: none;
		border-radius: 0.5rem;
		padding: 0.5rem 1rem;
		cursor: pointer;
	}

	.confirm-button:disabled {
		opacity: 0.5;
		cursor: default;
	}
</style>
