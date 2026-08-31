<script lang="ts">
	import { api, type NetworkTestConnectionResult } from '$lib/api';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialSettings: Record<string, unknown> | null;
	}

	let { initialSettings }: Props = $props();

	let hdhomerunTunerHostInput = $state('');
	let hdhomerunTunerPortInput = $state(80);
	let hdhomerunDvrHostInput = $state('');
	let hdhomerunDvrPortInput = $state(50000);
	const hdhomerunState = new SaveState();
	let hdhomerunTestingTuner = $state(false);
	let hdhomerunTunerTestResult = $state<NetworkTestConnectionResult | null>(null);
	let hdhomerunTestingDvr = $state(false);
	let hdhomerunDvrTestResult = $state<NetworkTestConnectionResult | null>(null);

	loadOnceWhen(
		() => initialSettings !== null,
		() => {
			hdhomerunTunerHostInput = (initialSettings!.tuner_host as string) ?? '';
			hdhomerunTunerPortInput = (initialSettings!.tuner_port as number) ?? 80;
			hdhomerunDvrHostInput = (initialSettings!.dvr_host as string) ?? '';
			hdhomerunDvrPortInput = (initialSettings!.dvr_port as number) ?? 50000;
		},
	);

	function hdhomerunFormSettings(): Record<string, unknown> {
		return {
			tuner_host: hdhomerunTunerHostInput,
			tuner_port: hdhomerunTunerPortInput,
			dvr_host: hdhomerunDvrHostInput,
			dvr_port: hdhomerunDvrPortInput,
		};
	}

	async function testHdhomerunTuner() {
		hdhomerunTestingTuner = true;
		hdhomerunTunerTestResult = null;
		try {
			hdhomerunTunerTestResult = await api.testHDHomeRunTunerConnection(hdhomerunFormSettings());
		} catch {
			hdhomerunTunerTestResult = { ok: false, detail: null, error: get(_)('common.backend_unreachable') };
		} finally {
			hdhomerunTestingTuner = false;
		}
	}

	async function testHdhomerunDvr() {
		hdhomerunTestingDvr = true;
		hdhomerunDvrTestResult = null;
		try {
			hdhomerunDvrTestResult = await api.testHDHomeRunDvrConnection(hdhomerunFormSettings());
		} catch {
			hdhomerunDvrTestResult = { ok: false, detail: null, error: get(_)('common.backend_unreachable') };
		} finally {
			hdhomerunTestingDvr = false;
		}
	}

	async function saveHdhomerun() {
		await hdhomerunState.run(
			async () => {
				await api.updateNetworkIntegration('hdhomerun', hdhomerunFormSettings());
			},
			get(_)('network_settings.save_error'),
			{ setSaved: false },
		);
	}
</script>

<section>
	<h3>{$_('network_settings.section_hdhomerun')}</h3>
	<h4>{$_('hdhomerun.detail.tuner_heading')}</h4>
	<label>
		{$_('hdhomerun.detail.host_label')}
		<input type="text" bind:value={hdhomerunTunerHostInput} placeholder="hdhomerun.local" />
	</label>
	<label>
		{$_('hdhomerun.detail.port_label')}
		<input type="number" min="1" max="65535" bind:value={hdhomerunTunerPortInput} />
	</label>
	<div class="test-row">
		<button class="test" disabled={hdhomerunTestingTuner} onclick={testHdhomerunTuner}>
			{hdhomerunTestingTuner ? $_('common.testing') : $_('common.test_connection')}
		</button>
		{#if hdhomerunTunerTestResult}
			{#if hdhomerunTunerTestResult.ok}
				<span class="test-result ok"
					>{$_('network_settings.test_ok', { values: { detail: hdhomerunTunerTestResult.detail } })}</span
				>
			{:else}
				<span class="test-result fail"
					>{$_('network_settings.test_fail', { values: { error: hdhomerunTunerTestResult.error } })}</span
				>
			{/if}
		{/if}
	</div>

	<h4>
		{$_('hdhomerun.detail.dvr_settings_heading')} <span class="optional">{$_('hdhomerun.detail.optional')}</span>
	</h4>
	<label>
		{$_('hdhomerun.detail.host_label')}
		<input type="text" bind:value={hdhomerunDvrHostInput} placeholder="dvr.local" />
	</label>
	<label>
		{$_('hdhomerun.detail.port_label')}
		<input type="number" min="1" max="65535" bind:value={hdhomerunDvrPortInput} />
	</label>
	<div class="test-row">
		<button class="test" disabled={hdhomerunTestingDvr} onclick={testHdhomerunDvr}>
			{hdhomerunTestingDvr ? $_('common.testing') : $_('common.test_connection')}
		</button>
		{#if hdhomerunDvrTestResult}
			{#if hdhomerunDvrTestResult.ok}
				<span class="test-result ok"
					>{$_('network_settings.test_ok', { values: { detail: hdhomerunDvrTestResult.detail } })}</span
				>
			{:else}
				<span class="test-result fail"
					>{$_('network_settings.test_fail', { values: { error: hdhomerunDvrTestResult.error } })}</span
				>
			{/if}
		{/if}
	</div>

	{#if hdhomerunState.error}
		<p class="hint error">{hdhomerunState.error}</p>
	{/if}

	<button class="save" disabled={hdhomerunState.saving} onclick={saveHdhomerun}>
		{hdhomerunState.saving ? $_('common.saving') : $_('common.save')}
	</button>
</section>
