<script lang="ts">
	import {
		api,
		type SchedulesDirectTestResult,
		type SchedulesDirectHeadend,
		type SchedulesDirectStation,
	} from '$lib/api';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialUsername: string | null;
		initialHasPassword: boolean | null;
		onStationsChanged: (stations: SchedulesDirectStation[]) => void;
	}

	let { initialUsername, initialHasPassword, onStationsChanged }: Props = $props();

	let sdUsernameInput = $state('');
	let sdPasswordInput = $state('');
	let sdHasPassword = $state(false);
	const sdState = new SaveState();
	let sdTesting = $state(false);
	let sdTestResult = $state<SchedulesDirectTestResult | null>(null);
	let sdPostalCodeInput = $state('');
	let sdHeadends = $state<SchedulesDirectHeadend[]>([]);
	let sdSearchingHeadends = $state(false);
	let sdHeadendsError = $state<string | null>(null);
	let sdAddingLineupId = $state<string | null>(null);
	let sdDeletingLineupId = $state<string | null>(null);

	loadOnceWhen(
		() => initialUsername !== null,
		() => {
			sdUsernameInput = initialUsername!;
			sdHasPassword = initialHasPassword ?? false;
		},
	);

	async function testSchedulesDirect() {
		sdTesting = true;
		sdTestResult = null;
		try {
			const payload: Record<string, unknown> = { username: sdUsernameInput };
			if (sdPasswordInput) payload.password = sdPasswordInput;
			sdTestResult = await api.testSchedulesDirectConnection(payload);
		} catch {
			sdTestResult = { ok: false, detail: null, error: get(_)('common.backend_unreachable') };
		} finally {
			sdTesting = false;
		}
	}

	async function saveSchedulesDirect() {
		await sdState.run(
			async () => {
				const payload: Record<string, unknown> = { username: sdUsernameInput };
				if (sdPasswordInput) {
					payload.password = sdPasswordInput;
				}
				const res = await api.updateNetworkIntegration('schedules_direct', payload);
				sdHasPassword = Boolean(res.settings.has_password);
				sdPasswordInput = '';
				api.getSchedulesDirectStations().then(onStationsChanged).catch(() => {});
			},
			get(_)('network_settings.save_error'),
			{ setSaved: false },
		);
	}

	async function searchSdHeadends() {
		if (!sdPostalCodeInput.trim()) return;
		sdSearchingHeadends = true;
		sdHeadendsError = null;
		try {
			sdHeadends = await api.getSchedulesDirectHeadends(sdPostalCodeInput.trim());
		} catch {
			sdHeadendsError = get(_)('network_settings.save_error');
		} finally {
			sdSearchingHeadends = false;
		}
	}

	async function addSdLineup(lineupId: string) {
		sdAddingLineupId = lineupId;
		try {
			await api.addSchedulesDirectLineup(lineupId);
			if (sdTestResult?.detail) {
				const lineups = await api.getSchedulesDirectLineups();
				sdTestResult.detail.lineups = lineups;
			}
			api.getSchedulesDirectStations().then(onStationsChanged).catch(() => {});
		} catch {
			sdState.error = get(_)('network_settings.save_error');
		} finally {
			sdAddingLineupId = null;
		}
	}

	async function deleteSdLineup(lineupId: string) {
		sdDeletingLineupId = lineupId;
		try {
			await api.deleteSchedulesDirectLineup(lineupId);
			if (sdTestResult?.detail) {
				const lineups = await api.getSchedulesDirectLineups();
				sdTestResult.detail.lineups = lineups;
			}
			api.getSchedulesDirectStations().then(onStationsChanged).catch(() => {});
		} catch {
			sdState.error = get(_)('network_settings.save_error');
		} finally {
			sdDeletingLineupId = null;
		}
	}
</script>

<section>
	<h3>{$_('network_settings.section_schedules_direct')}</h3>
	<p class="hint">{$_('network_settings.schedules_direct_hint')}</p>

	<label>
		{$_('network_settings.sd_username_label')}
		<input type="text" bind:value={sdUsernameInput} placeholder="username" />
	</label>
	<label>
		{$_('network_settings.sd_password_label')}
		<input type="password" bind:value={sdPasswordInput} placeholder={sdHasPassword ? '(unchanged)' : ''} />
	</label>

	<div class="test-row">
		<button class="test" disabled={sdTesting} onclick={testSchedulesDirect}>
			{sdTesting ? $_('network_settings.sd_testing') : $_('network_settings.sd_test_connection')}
		</button>
		{#if sdTestResult}
			{#if sdTestResult.ok}
				<span class="test-result ok">
					{$_('network_settings.test_ok', { values: { detail: sdTestResult.detail?.expires ? $_('network_settings.sd_account_expires', { values: { expires: new Date(sdTestResult.detail.expires).toLocaleDateString() } }) : 'OK' } })}
				</span>
			{:else}
				<span class="test-result fail">
					{$_('network_settings.test_fail', { values: { error: sdTestResult.error } })}
				</span>
			{/if}
		{/if}
	</div>

	{#if sdTestResult?.detail?.lineups}
		<div class="sd-lineups-container">
			<h4>{$_('network_settings.sd_active_lineups')}</h4>
			{#if sdTestResult.detail.lineups.length === 0}
				<p class="hint">{$_('network_settings.sd_no_active_lineups')}</p>
			{:else}
				<ul class="sd-lineups-list">
					{#each sdTestResult.detail.lineups as lineup (lineup.lineup)}
						<li class="sd-lineup-item">
							<span>{lineup.name} ({lineup.lineup})</span>
							<button
								type="button"
								class="clear small"
								disabled={sdDeletingLineupId === lineup.lineup}
								onclick={() => deleteSdLineup(lineup.lineup)}
							>
								{$_('network_settings.sd_remove_lineup')}
							</button>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{/if}

	<div class="sd-search-headends-container">
		<h4>{$_('network_settings.sd_search_headends_heading')}</h4>
		<div class="sd-search-row">
			<input
				type="text"
				bind:value={sdPostalCodeInput}
				placeholder={$_('network_settings.sd_postal_code_placeholder')}
			/>
			<button
				type="button"
				class="test"
				disabled={sdSearchingHeadends || !sdPostalCodeInput.trim()}
				onclick={searchSdHeadends}
			>
				{sdSearchingHeadends ? $_('network_settings.sd_searching') : $_('network_settings.sd_search_button')}
			</button>
		</div>

		{#if sdHeadendsError}
			<p class="hint error">{sdHeadendsError}</p>
		{/if}

		{#if sdHeadends.length > 0}
			<div class="sd-headends-results">
				{#each sdHeadends as headend (headend.headend)}
					{#each headend.lineups as lineup (lineup.lineup)}
						<div class="sd-headend-result-item">
							<span>{lineup.name} ({lineup.lineup})</span>
							<button
								type="button"
								class="save small"
								disabled={sdAddingLineupId === lineup.lineup}
								onclick={() => addSdLineup(lineup.lineup)}
							>
								{$_('network_settings.sd_add_lineup_button')}
							</button>
						</div>
					{/each}
				{/each}
			</div>
		{/if}
	</div>

	{#if sdState.error}
		<p class="hint error">{sdState.error}</p>
	{/if}

	<button class="save" disabled={sdState.saving} onclick={saveSchedulesDirect}>
		{sdState.saving ? $_('common.saving') : $_('common.save')}
	</button>
</section>

<style>
	.sd-lineups-container,
	.sd-search-headends-container {
		margin-top: 0.75rem;
		padding: 0.5rem 0;
		border-top: 1px solid var(--color-border);
	}

	.sd-lineups-container h4,
	.sd-search-headends-container h4 {
		margin: 0 0 0.5rem;
		font-size: 0.9rem;
		font-weight: 600;
	}

	.sd-lineups-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.sd-lineup-item,
	.sd-headend-result-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.35rem 0.5rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.35rem;
		font-size: 0.85rem;
	}

	.sd-search-row {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.sd-headends-results {
		margin-top: 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
</style>
