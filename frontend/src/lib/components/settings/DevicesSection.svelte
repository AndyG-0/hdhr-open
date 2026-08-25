<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type DeviceListEntry } from '$lib/api';
	import { device as currentDevice, renameDevice as renameCurrentDevice } from '$lib/stores/device';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	let devices = $state<DeviceListEntry[]>([]);
	let devicesError = $state<string | null>(null);
	let deviceNameInput = $state('');
	let savingDeviceName = $state(false);
	let confirmingForgetDeviceId = $state<string | null>(null);
	let forgettingDeviceId = $state<string | null>(null);
	let renamingDevice = $state(false);
	let renameDialogEl = $state<HTMLDivElement | null>(null);

	function cancelRenameDevice() {
		renamingDevice = false;
		deviceNameInput = $currentDevice?.name ?? '';
	}

	function handleRenameDialogPointerDown(e: PointerEvent) {
		if (renamingDevice && renameDialogEl && e.target instanceof Node && !renameDialogEl.contains(e.target)) {
			cancelRenameDevice();
		}
	}

	function handleRenameDialogKeydown(e: KeyboardEvent) {
		if (renamingDevice && e.key === 'Escape') cancelRenameDevice();
	}

	loadOnceWhen(
		() => !!$currentDevice,
		() => {
			deviceNameInput = $currentDevice!.name;
		},
	);

	async function loadDevices() {
		try {
			devices = await api.listDevices();
		} catch {
			devicesError = get(_)('settings.devices.load_error');
		}
	}

	onMount(() => {
		loadDevices();
	});

	async function saveDeviceName() {
		savingDeviceName = true;
		devicesError = null;
		try {
			await renameCurrentDevice(deviceNameInput.trim());
			await loadDevices();
			renamingDevice = false;
		} catch {
			devicesError = get(_)('settings.devices.rename_error');
		} finally {
			savingDeviceName = false;
		}
	}

	async function forgetDevice(id: string) {
		forgettingDeviceId = id;
		devicesError = null;
		try {
			await api.deleteDevice(id);
			devices = devices.filter((d) => d.id !== id);
		} catch {
			devicesError = get(_)('settings.devices.forget_error');
		} finally {
			forgettingDeviceId = null;
			confirmingForgetDeviceId = null;
		}
	}
</script>

<svelte:window onpointerdown={handleRenameDialogPointerDown} onkeydown={handleRenameDialogKeydown} />

<section>
	<h3>{$_('settings.devices.heading')}</h3>

	{#if devicesError}
		<p class="hint error">{devicesError}</p>
	{/if}

	{#if devices.length > 0}
		<ul class="device-list">
			{#each devices as d (d.id)}
				<li>
					<span class="device-name">{d.name}</span>
					{#if d.id === $currentDevice?.id}
						<span class="device-actions">
							<span class="hint">({$_('settings.devices.this_device_label')})</span>
							<button type="button" class="link-button" onclick={() => (renamingDevice = true)}>
								{$_('settings.devices.rename')}
							</button>
						</span>
					{:else if confirmingForgetDeviceId === d.id}
						<span class="confirm-actions">
							<button
								class="cancel"
								onclick={() => (confirmingForgetDeviceId = null)}
								disabled={forgettingDeviceId === d.id}
							>
								{$_('common.cancel')}
							</button>
							<button class="danger" onclick={() => forgetDevice(d.id)} disabled={forgettingDeviceId === d.id}>
								{forgettingDeviceId === d.id ? $_('settings.devices.forgetting') : $_('settings.devices.forget')}
							</button>
						</span>
					{:else}
						<button class="danger-link" onclick={() => (confirmingForgetDeviceId = d.id)}
							>{$_('settings.devices.forget_device')}</button
						>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

{#if renamingDevice}
	<div class="rename-device-backdrop"></div>
	<div class="rename-device-dialog" bind:this={renameDialogEl} role="dialog" aria-label={$_('settings.devices.rename')}>
		<h4>{$_('settings.devices.rename')}</h4>
		<input type="text" bind:value={deviceNameInput} maxlength="40" />
		<div class="rename-device-actions">
			<button type="button" class="cancel" onclick={cancelRenameDevice}>
				{$_('common.cancel')}
			</button>
			<button class="save" disabled={savingDeviceName || !deviceNameInput.trim()} onclick={saveDeviceName}>
				{savingDeviceName ? $_('common.saving') : $_('common.save')}
			</button>
		</div>
	</div>
{/if}

<style>
	.device-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.device-list li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.device-name {
		font-size: 0.9rem;
	}

	.device-actions {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.link-button {
		background: none;
		border: none;
		color: var(--color-accent);
		text-decoration: underline;
		cursor: pointer;
		padding: 0;
		font-size: 0.85rem;
	}

	.rename-device-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.5);
		z-index: 100;
	}

	.rename-device-dialog {
		position: fixed;
		z-index: 101;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: 20rem;
		max-width: calc(100vw - 3rem);
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 1rem;
		padding: 1.5rem;
	}

	.rename-device-dialog h4 {
		margin: 0;
	}

	.rename-device-actions {
		display: flex;
		justify-content: flex-end;
		gap: 0.5rem;
	}

	.rename-device-actions .cancel {
		background: none;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0.5rem 0.75rem;
		font-size: 0.9rem;
	}
</style>
