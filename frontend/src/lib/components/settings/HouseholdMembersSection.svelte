<script lang="ts">
	import { api, type HouseholdUser } from '$lib/api';
	import { user } from '$lib/stores/user';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	let householdUsers = $state<HouseholdUser[]>([]);
	let householdError = $state<string | null>(null);
	let householdLoading = $state(false);
	let updatingRoleId = $state<string | null>(null);
	let confirmingRemoveId = $state<string | null>(null);
	let removingId = $state<string | null>(null);

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
			householdError = 'Could not load household members.';
		} finally {
			householdLoading = false;
		}
	}

	async function toggleRole(member: HouseholdUser) {
		const nextRole = member.role === 'admin' ? 'member' : 'admin';
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
						? "Can't demote the last remaining admin."
						: 'Could not update role.';
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
		} catch {
			householdError = 'Could not remove this member.';
		} finally {
			removingId = null;
			confirmingRemoveId = null;
		}
	}
</script>

<section>
	<h3>Household members</h3>
	{#if householdError}
		<p class="hint error">{householdError}</p>
	{/if}
	{#if householdLoading && householdUsers.length === 0}
		<p class="hint">Loading…</p>
	{:else}
		<ul class="member-list">
			{#each householdUsers as member (member.id)}
				<li>
					<span class="member-info">
						<span class="avatar-sm">{member.avatar || member.name.charAt(0).toUpperCase()}</span>
						<span class="member-name">{member.name}</span>
						<span class="role-badge" class:admin={member.role === 'admin'}>{member.role}</span>
					</span>
					{#if $user && member.id === $user.id}
						<span class="hint">(you)</span>
					{:else}
						<span class="member-actions">
							<button class="clear" onclick={() => toggleRole(member)} disabled={updatingRoleId === member.id}>
								{member.role === 'admin' ? 'Demote to member' : 'Promote to admin'}
							</button>
							{#if confirmingRemoveId === member.id}
								<span class="confirm-actions">
									<button
										class="cancel"
										onclick={() => (confirmingRemoveId = null)}
										disabled={removingId === member.id}
									>
										Cancel
									</button>
									<button
										class="danger"
										onclick={() => removeMember(member.id)}
										disabled={removingId === member.id}
									>
										{removingId === member.id ? 'Removing…' : 'Remove'}
									</button>
								</span>
							{:else}
								<button class="danger-link" onclick={() => (confirmingRemoveId = member.id)}>Remove</button>
							{/if}
						</span>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.member-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.member-list li {
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

	.member-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
</style>
