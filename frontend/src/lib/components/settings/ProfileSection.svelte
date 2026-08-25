<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api';
	import { user, logout } from '$lib/stores/user';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	let profileNameInput = $state('');
	let profileAvatarInput = $state('');
	let profilePinInput = $state('');
	let profileHasPin = $state(false);
	const profileState = new SaveState();
	let confirmingDeleteProfile = $state(false);
	let deletingProfile = $state(false);

	// $user loads asynchronously (see +layout.svelte's gate), so seed these
	// inputs the first time it becomes available rather than in onMount.
	loadOnceWhen(
		() => !!$user,
		() => {
			profileNameInput = $user!.name;
			profileAvatarInput = $user!.avatar ?? '';
			const currentUserId = $user!.id;
			api
				.listUsers()
				.then((profiles) => {
					profileHasPin = profiles.find((p) => p.id === currentUserId)?.has_pin ?? false;
				})
				.catch(() => {
					// leave the PIN section assuming no PIN is set
				});
		},
	);

	async function saveProfile() {
		if (profilePinInput && !/^\d{4,8}$/.test(profilePinInput)) {
			profileState.error = get(_)('settings.profile.pin_invalid');
			return;
		}
		await profileState.run(async () => {
			const partial: { name?: string; avatar?: string; pin?: string } = {
				name: profileNameInput.trim(),
				avatar: profileAvatarInput.trim(),
			};
			if (profilePinInput) partial.pin = profilePinInput;
			const updated = await api.updateUser(partial);
			user.set(updated);
			if (profilePinInput) profileHasPin = true;
			profilePinInput = '';
		}, get(_)('settings.profile.save_error'));
	}

	async function clearPin() {
		profileState.error = null;
		try {
			const updated = await api.updateUser({ pin: '' });
			user.set(updated);
			profileHasPin = false;
		} catch {
			profileState.error = get(_)('settings.profile.clear_pin_error');
		}
	}

	async function deleteProfile() {
		deletingProfile = true;
		profileState.error = null;
		try {
			await api.deleteUser();
			await logout().catch(() => {});
			goto('/login');
		} catch {
			profileState.error = get(_)('settings.profile.delete_error');
			deletingProfile = false;
			confirmingDeleteProfile = false;
		}
	}
</script>

<section>
	<h3>{$_('settings.profile.heading')}</h3>
	<label>
		{$_('settings.profile.name_label')}
		<input type="text" bind:value={profileNameInput} maxlength="40" />
	</label>
	<label>
		{$_('settings.profile.avatar_label')}
		<input type="text" bind:value={profileAvatarInput} placeholder="🐱" maxlength="8" />
	</label>
	<label>
		{$_('settings.profile.pin_label')}
		<input
			type="password"
			inputmode="numeric"
			bind:value={profilePinInput}
			placeholder={profileHasPin ? $_('common.password_set_hint') : $_('settings.profile.pin_not_set')}
			maxlength="8"
		/>
	</label>
	{#if profileHasPin}
		<button class="clear" onclick={clearPin}>{$_('settings.profile.clear_pin')}</button>
	{/if}
	{#if profileState.error}
		<p class="hint error">{profileState.error}</p>
	{/if}
	{#if profileState.saved}
		<p class="hint">{$_('common.saved')}</p>
	{/if}
	<button class="save" disabled={profileState.saving || !profileNameInput.trim()} onclick={saveProfile}>
		{profileState.saving ? $_('common.saving') : $_('settings.profile.save')}
	</button>

	{#if confirmingDeleteProfile}
		<p class="hint error">{$_('settings.profile.delete_confirm')}</p>
		<div class="confirm-actions">
			<button class="cancel" onclick={() => (confirmingDeleteProfile = false)} disabled={deletingProfile}>
				{$_('common.cancel')}
			</button>
			<button class="danger" onclick={deleteProfile} disabled={deletingProfile}>
				{deletingProfile ? $_('settings.profile.deleting') : $_('settings.profile.delete')}
			</button>
		</div>
	{:else}
		<button class="danger-link" onclick={() => (confirmingDeleteProfile = true)}
			>{$_('settings.profile.delete_link')}</button
		>
	{/if}
</section>
