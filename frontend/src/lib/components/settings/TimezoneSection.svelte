<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialTimezone: string | null;
	}

	let { initialTimezone }: Props = $props();

	let timezoneInput = $state('UTC');
	let timezoneOptions = $state<string[]>(['UTC']);
	const timezoneState = new SaveState();

	loadOnceWhen(
		() => initialTimezone !== null,
		() => {
			timezoneInput = initialTimezone!;
			if (!timezoneOptions.includes(timezoneInput)) timezoneOptions = [timezoneInput, ...timezoneOptions];
		},
	);

	onMount(() => {
		try {
			// Intl.supportedValuesOf isn't in every browser's types yet, but is
			// available in the Chromium the kiosk runs — avoids shipping a
			// hardcoded IANA timezone list.
			const supported = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.(
				'timeZone',
			);
			if (supported?.length) timezoneOptions = supported;
		} catch {
			// keep the UTC-only fallback
		}
	});

	async function saveTimezone() {
		await timezoneState.run(async () => {
			await api.updateSettings({ timezone: timezoneInput });
		}, 'Could not save timezone.');
	}
</script>

<section>
	<h3>Timezone</h3>
	<label>
		Used to schedule recordings and display program times
		<select bind:value={timezoneInput}>
			{#each timezoneOptions as tz (tz)}
				<option value={tz}>{tz}</option>
			{/each}
		</select>
	</label>

	{#if timezoneState.error}
		<p class="hint error">{timezoneState.error}</p>
	{/if}
	{#if timezoneState.saved}
		<p class="hint">Saved.</p>
	{/if}
	<button class="save" disabled={timezoneState.saving} onclick={saveTimezone}>
		{timezoneState.saving ? 'Saving…' : 'Save timezone'}
	</button>
</section>
