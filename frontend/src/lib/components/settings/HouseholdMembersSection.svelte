<script lang="ts">
	import { api, type HouseholdUser, type UserRole } from '$lib/api';
	import { user } from '$lib/stores/user';
	import { loadOnceWhen } from '$lib/load-once.svelte';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';

	let householdUsers = $state<HouseholdUser[]>([]);
	let householdError = $state<string | null>(null);
	let householdLoading = $state(false);
	let updatingRoleId = $state<string | null>(null);
	let confirmingRemoveId = $state<string | null>(null);
	let removingId = $state<string | null>(null);

	// Add member state
	let showAddForm = $state(false);
	let addName = $state('');
	let addAvatar = $state('');
	let addRole = $state<UserRole>('member');
	let addPin = $state('');
	let addLoading = $state(false);
	let addError = $state<string | null>(null);

	// Edit member state
	let editingId = $state<string | null>(null);
	let editName = $state('');
	let editAvatar = $state('');
	let editRole = $state<UserRole>('member');
	let editPin = $state('');
	let editClearPin = $state(false);
	let editLoading = $state(false);
	let editError = $state<string | null>(null);

	loadOnceWhen(
		() => $user?.role === 'admin',
		loadHouseholdUsers,
	);

	async function loadHouseholdUsers() {
		householdLoading = true;
		householdError = null;
		try {
			householdUsers = await api.listHouseholdUsers();
		} catch {
			householdError = get(_)('settings.household_members.load_error');
		} finally {
			householdLoading = false;
		}
	}

	async function toggleRole(member: HouseholdUser) {
		const nextRole: UserRole = member.role === 'admin' ? 'member' : 'admin';
		updatingRoleId = member.id;
		householdError = null;
		try {
			const updated = await api.updateUserRole(member.id, nextRole);
			householdUsers = householdUsers.map((existing) => (existing.id === member.id ? updated : existing));
		} catch (err) {
			householdError =
				err instanceof Error && err.message
					? err.message
					: member.role === 'admin'
						? get(_)('settings.household_members.last_admin_demote_error')
						: get(_)('settings.household_members.save_error');
		} finally {
			updatingRoleId = null;
		}
	}

	async function removeMember(id: string) {
		removingId = id;
		householdError = null;
		try {
			await api.removeHouseholdUser(id);
			householdUsers = householdUsers.filter((u) => u.id !== id);
			if (editingId === id) editingId = null;
		} catch {
			householdError = get(_)('settings.household_members.remove_error');
		} finally {
			removingId = null;
			confirmingRemoveId = null;
		}
	}

	async function handleCreateUser() {
		const trimmedName = addName.trim();
		if (!trimmedName) return;

		if (addPin && !/^\d{4,8}$/.test(addPin)) {
			addError = get(_)('settings.household_members.pin_invalid');
			return;
		}

		addLoading = true;
		addError = null;
		try {
			const created = await api.createHouseholdUser({
				name: trimmedName,
				avatar: addAvatar.trim() || null,
				role: addRole,
				pin: addPin || undefined,
			});
			householdUsers = [...householdUsers, created];
			cancelAdd();
		} catch (err) {
			addError =
				err instanceof Error && err.message ? err.message : get(_)('settings.household_members.create_error');
		} finally {
			addLoading = false;
		}
	}

	function cancelAdd() {
		showAddForm = false;
		addName = '';
		addAvatar = '';
		addRole = 'member';
		addPin = '';
		addError = null;
	}

	function startEditing(member: HouseholdUser) {
		editingId = member.id;
		editName = member.name;
		editAvatar = member.avatar ?? '';
		editRole = member.role;
		editPin = '';
		editClearPin = false;
		editError = null;
	}

	function cancelEditing() {
		editingId = null;
		editName = '';
		editAvatar = '';
		editRole = 'member';
		editPin = '';
		editClearPin = false;
		editError = null;
	}

	async function handleSaveEdit(member: HouseholdUser) {
		const trimmedName = editName.trim();
		if (!trimmedName) return;

		if (editPin && !/^\d{4,8}$/.test(editPin)) {
			editError = get(_)('settings.household_members.pin_invalid');
			return;
		}

		const adminCount = householdUsers.filter((u) => u.role === 'admin').length;
		if (member.role === 'admin' && editRole !== 'admin' && adminCount <= 1) {
			editError = get(_)('settings.household_members.last_admin_demote_error');
			return;
		}

		editLoading = true;
		editError = null;
		try {
			const payload: {
				name?: string;
				avatar?: string | null;
				role?: UserRole;
				pin?: string | null;
			} = {
				name: trimmedName,
				avatar: editAvatar.trim() || null,
				role: editRole,
			};

			if (editClearPin) {
				payload.pin = '';
			} else if (editPin) {
				payload.pin = editPin;
			}

			const updated = await api.updateHouseholdUser(member.id, payload);
			householdUsers = householdUsers.map((existing) => (existing.id === member.id ? updated : existing));

			if ($user && member.id === $user.id) {
				user.update((u) => (u ? { ...u, name: updated.name, avatar: updated.avatar, role: updated.role } : null));
			}

			cancelEditing();
		} catch (err) {
			editError =
				err instanceof Error && err.message ? err.message : get(_)('settings.household_members.save_error');
		} finally {
			editLoading = false;
		}
	}
</script>

<section>
	<div class="section-header">
		<h3>{$_('settings.household_members.heading')}</h3>
		{#if !showAddForm}
			<button class="save" onclick={() => (showAddForm = true)}>
				+ {$_('settings.household_members.add_member')}
			</button>
		{/if}
	</div>

	{#if householdError}
		<p class="hint error">{householdError}</p>
	{/if}

	{#if showAddForm}
		<div class="user-form add-form" aria-label={$_('settings.household_members.add_member')}>
			<h4>{$_('settings.household_members.add_member')}</h4>
			<label>
				{$_('settings.household_members.name_label')}
				<input type="text" bind:value={addName} placeholder="Alice" maxlength="40" />
			</label>
			<label>
				{$_('settings.household_members.avatar_label')}
				<input type="text" bind:value={addAvatar} placeholder="🐱" maxlength="8" />
			</label>
			<label>
				{$_('settings.household_members.role_label')}
				<select bind:value={addRole}>
					<option value="member">{$_('settings.household_members.role_member')}</option>
					<option value="admin">{$_('settings.household_members.role_admin')}</option>
				</select>
			</label>
			<label>
				{$_('settings.household_members.pin_label')}
				<input
					type="password"
					inputmode="numeric"
					bind:value={addPin}
					placeholder={$_('settings.household_members.pin_placeholder')}
					maxlength="8"
				/>
			</label>

			{#if addError}
				<p class="hint error">{addError}</p>
			{/if}

			<div class="form-actions">
				<button class="cancel" onclick={cancelAdd} disabled={addLoading}>
					{$_('settings.household_members.cancel')}
				</button>
				<button class="save" onclick={handleCreateUser} disabled={addLoading || !addName.trim()}>
					{addLoading ? $_('settings.household_members.creating') : $_('settings.household_members.create')}
				</button>
			</div>
		</div>
	{/if}

	{#if householdLoading && householdUsers.length === 0}
		<p class="hint">{$_('common.loading')}</p>
	{:else}
		<ul class="member-list">
			{#each householdUsers as member (member.id)}
				<li class="member-item">
					<div class="member-main">
						<span class="member-info">
							<span class="avatar-sm">{member.avatar || member.name.charAt(0).toUpperCase()}</span>
							<span class="member-name">{member.name}</span>
							<span class="role-badge" class:admin={member.role === 'admin'}>{member.role}</span>
							{#if member.has_pin}
								<span class="pin-badge" title={$_('settings.household_members.pin_set')}>🔒</span>
							{/if}
						</span>
						<span class="member-actions">
							{#if $user && member.id === $user.id}
								<span class="hint">(you)</span>
							{:else}
								<button
									class="clear"
									onclick={() => toggleRole(member)}
									disabled={updatingRoleId === member.id}
								>
									{member.role === 'admin'
										? $_('settings.household_members.demote')
										: $_('settings.household_members.promote')}
								</button>
							{/if}
							<button
								class="clear"
								onclick={() => (editingId === member.id ? cancelEditing() : startEditing(member))}
								disabled={editingId === member.id}
							>
								{$_('settings.household_members.edit_member')}
							</button>
							{#if !$user || member.id !== $user.id}
								{#if confirmingRemoveId === member.id}
									<span class="confirm-actions">
										<button
											class="cancel"
											onclick={() => (confirmingRemoveId = null)}
											disabled={removingId === member.id}
										>
											{$_('settings.household_members.cancel')}
										</button>
										<button
											class="danger"
											onclick={() => removeMember(member.id)}
											disabled={removingId === member.id}
										>
											{removingId === member.id
												? $_('settings.household_members.removing')
												: $_('settings.household_members.remove')}
										</button>
									</span>
								{:else}
									<button class="danger-link" onclick={() => (confirmingRemoveId = member.id)}>
										{$_('settings.household_members.remove')}
									</button>
								{/if}
							{/if}
						</span>
					</div>

					{#if editingId === member.id}
						<div class="user-form edit-form" aria-label={$_('settings.household_members.edit_member')}>
							<h4>{$_('settings.household_members.edit_member')}: {member.name}</h4>
							<label>
								{$_('settings.household_members.name_label')}
								<input type="text" bind:value={editName} maxlength="40" />
							</label>
							<label>
								{$_('settings.household_members.avatar_label')}
								<input type="text" bind:value={editAvatar} placeholder="🐱" maxlength="8" />
							</label>
							<label>
								{$_('settings.household_members.role_label')}
								<select
									bind:value={editRole}
									disabled={member.role === 'admin' &&
										householdUsers.filter((u) => u.role === 'admin').length <= 1}
								>
									<option value="member">{$_('settings.household_members.role_member')}</option>
									<option value="admin">{$_('settings.household_members.role_admin')}</option>
								</select>
							</label>

							<div class="pin-management-field">
								<span class="pin-status">
									{member.has_pin
										? $_('settings.household_members.pin_set')
										: $_('settings.household_members.pin_not_set')}
								</span>
								{#if member.has_pin}
									<label class="checkbox-label">
										<input
											type="checkbox"
											bind:checked={editClearPin}
											onchange={() => {
												if (editClearPin) editPin = '';
											}}
										/>
										{$_('settings.household_members.clear_pin')}
									</label>
								{/if}
								{#if !editClearPin}
									<label>
										{$_('settings.household_members.pin_label')}
										<input
											type="password"
											inputmode="numeric"
											bind:value={editPin}
											placeholder={$_('settings.household_members.pin_reset_placeholder')}
											maxlength="8"
										/>
									</label>
								{/if}
							</div>

							{#if editError}
								<p class="hint error">{editError}</p>
							{/if}

							<div class="form-actions">
								<button class="cancel" onclick={cancelEditing} disabled={editLoading}>
									{$_('settings.household_members.cancel')}
								</button>
								<button
									class="save"
									onclick={() => handleSaveEdit(member)}
									disabled={editLoading || !editName.trim()}
								>
									{editLoading ? $_('settings.household_members.saving') : $_('settings.household_members.save')}
								</button>
							</div>
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.section-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1rem;
	}

	.section-header h3 {
		margin: 0;
	}

	.member-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.member-item {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		border-bottom: 1px solid var(--color-border);
		padding-bottom: 0.75rem;
	}

	.member-item:last-child {
		border-bottom: none;
		padding-bottom: 0;
	}

	.member-main {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.member-info {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.avatar-sm {
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 50%;
		background: var(--color-surface-hover, var(--color-border));
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1rem;
	}

	.member-name {
		font-size: 0.9rem;
	}

	.role-badge {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: var(--color-text-muted);
		border: 1px solid var(--color-border);
		border-radius: 999px;
		padding: 0.1rem 0.5rem;
	}

	.role-badge.admin {
		color: var(--color-accent);
		border-color: var(--color-accent);
	}

	.pin-badge {
		font-size: 0.8rem;
		opacity: 0.75;
	}

	.member-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.user-form {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding: 1rem;
		background: var(--color-surface, rgba(255, 255, 255, 0.03));
		border: 1px solid var(--color-border);
		border-radius: 8px;
		margin: 0.5rem 0;
	}

	.user-form h4 {
		margin: 0 0 0.25rem;
		font-size: 0.95rem;
	}

	.user-form label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.user-form input[type='text'],
	.user-form input[type='password'],
	.user-form select {
		padding: 0.4rem 0.6rem;
		border: 1px solid var(--color-border);
		border-radius: 4px;
		background: var(--color-bg);
		color: inherit;
		font-size: 0.9rem;
	}

	.pin-management-field {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin-top: 0.25rem;
	}

	.pin-status {
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.checkbox-label {
		display: flex !important;
		flex-direction: row !important;
		align-items: center;
		gap: 0.5rem;
		cursor: pointer;
	}

	.checkbox-label input[type='checkbox'] {
		cursor: pointer;
	}

	.form-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 0.5rem;
	}
</style>
