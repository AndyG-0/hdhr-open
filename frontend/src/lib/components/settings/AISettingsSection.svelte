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

	let aiProviderInput = $state('openai');
	let aiApiKeyInput = $state('');
	let aiHasApiKey = $state(false);
	let aiBaseUrlInput = $state('');
	let aiModelInput = $state('');
	let aiTemperatureInput = $state(0.7);
	let aiSystemPromptInput = $state('');
	let aiEnableRecordingToolsInput = $state(false);
	const aiState = new SaveState();
	let aiTesting = $state(false);
	let aiTestResult = $state<NetworkTestConnectionResult | null>(null);
	// Fetched live from the configured provider rather than a hardcoded list,
	// which goes stale the moment a provider ships a new model — the model
	// input stays free-text either way, this just supplies fresh suggestions.
	let aiAvailableModels = $state<string[]>([]);
	let aiModelsLoading = $state(false);
	let aiModelsError = $state<string | null>(null);

	loadOnceWhen(
		() => initialSettings !== null,
		() => {
			aiProviderInput = (initialSettings!.provider as string) || 'openai';
			aiBaseUrlInput = (initialSettings!.base_url as string) ?? '';
			aiModelInput = (initialSettings!.model as string) ?? '';
			aiTemperatureInput = (initialSettings!.temperature as number) ?? 0.7;
			aiSystemPromptInput = (initialSettings!.system_prompt_custom as string) ?? '';
			aiEnableRecordingToolsInput = (initialSettings!.enable_recording_tools as boolean) ?? false;
			aiHasApiKey = Boolean(initialSettings!.has_api_key);
		},
	);

	function aiFormSettings(): Record<string, unknown> {
		const settings: Record<string, unknown> = {
			provider: aiProviderInput,
			base_url: aiBaseUrlInput,
			model: aiModelInput,
			temperature: aiTemperatureInput,
			system_prompt_custom: aiSystemPromptInput,
			enable_recording_tools: aiEnableRecordingToolsInput,
		};
		// Write-only secret — only send a new value when the user actually
		// typed one, so an empty field on save doesn't clear a saved key.
		if (aiApiKeyInput) settings.api_key = aiApiKeyInput;
		return settings;
	}

	async function fetchAiModels() {
		aiModelsLoading = true;
		aiModelsError = null;
		try {
			const res = await api.listAIModels(aiFormSettings());
			if (res.ok) {
				aiAvailableModels = res.models;
			} else {
				aiModelsError = res.error || get(_)('network_settings.ai_fetch_models_error');
			}
		} catch {
			aiModelsError = get(_)('common.backend_unreachable');
		} finally {
			aiModelsLoading = false;
		}
	}

	async function testAi() {
		aiTesting = true;
		aiTestResult = null;
		try {
			aiTestResult = await api.testAIConnection(aiFormSettings());
		} catch {
			aiTestResult = { ok: false, detail: null, error: get(_)('common.backend_unreachable') };
		} finally {
			aiTesting = false;
		}
	}

	async function saveAi() {
		await aiState.run(
			async () => {
				const res = await api.updateNetworkIntegration('ai', aiFormSettings());
				aiHasApiKey = Boolean(res.settings.has_api_key);
				aiApiKeyInput = '';
			},
			get(_)('network_settings.save_error'),
			{ setSaved: false },
		);
	}
</script>

<section>
	<h3>{$_('network_settings.section_ai')}</h3>
	<p class="hint">{$_('network_settings.ai_hint')}</p>

	<label>
		{$_('network_settings.ai_provider_label')}
		<select bind:value={aiProviderInput}>
			<option value="openai">{$_('network_settings.ai_provider_openai')}</option>
			<option value="anthropic">{$_('network_settings.ai_provider_anthropic')}</option>
			<option value="gemini">{$_('network_settings.ai_provider_gemini')}</option>
			<option value="custom">{$_('network_settings.ai_provider_custom')}</option>
		</select>
	</label>

	<label>
		{$_('network_settings.ai_api_key_label')}
		<input type="password" bind:value={aiApiKeyInput} placeholder={aiHasApiKey ? '(unchanged)' : ''} />
	</label>

	{#if aiProviderInput === 'custom'}
		<label>
			{$_('network_settings.ai_base_url_label')}
			<input type="text" bind:value={aiBaseUrlInput} placeholder="http://localhost:11434/v1" />
		</label>
		<p class="hint">{$_('network_settings.ai_base_url_hint')}</p>
	{/if}

	<label>
		{$_('network_settings.ai_model_label')}
		<input type="text" bind:value={aiModelInput} list="ai-model-options" />
	</label>
	<datalist id="ai-model-options">
		{#each aiAvailableModels as model (model)}
			<option value={model}></option>
		{/each}
	</datalist>

	<div class="test-row">
		<button
			type="button"
			class="test"
			disabled={aiModelsLoading || (!aiApiKeyInput && !aiHasApiKey)}
			onclick={fetchAiModels}
		>
			{aiModelsLoading ? $_('network_settings.ai_fetch_models_loading') : $_('network_settings.ai_fetch_models_label')}
		</button>
	</div>
	{#if aiModelsError}
		<p class="hint error">{aiModelsError}</p>
	{:else if aiAvailableModels.length > 0}
		<p class="hint">
			{$_('network_settings.ai_fetch_models_count', { values: { count: aiAvailableModels.length } })}
		</p>
	{/if}

	<label>
		{$_('network_settings.ai_temperature_label')}: {aiTemperatureInput.toFixed(1)}
		<input type="range" min="0" max="2" step="0.1" bind:value={aiTemperatureInput} />
	</label>

	<label>
		{$_('network_settings.ai_system_prompt_label')}
		<textarea bind:value={aiSystemPromptInput} rows="3"></textarea>
	</label>
	<p class="hint">{$_('network_settings.ai_system_prompt_hint')}</p>

	<label>
		<input type="checkbox" bind:checked={aiEnableRecordingToolsInput} />
		{$_('network_settings.ai_enable_recording_tools_label')}
	</label>

	<div class="test-row">
		<button class="test" disabled={aiTesting} onclick={testAi}>
			{aiTesting ? $_('common.testing') : $_('common.test_connection')}
		</button>
		{#if aiTestResult}
			{#if aiTestResult.ok}
				<span class="test-result ok">{$_('network_settings.test_ok', { values: { detail: aiTestResult.detail } })}</span
				>
			{:else}
				<span class="test-result fail"
					>{$_('network_settings.test_fail', { values: { error: aiTestResult.error } })}</span
				>
			{/if}
		{/if}
	</div>

	{#if aiState.error}
		<p class="hint error">{aiState.error}</p>
	{/if}

	<button class="save" disabled={aiState.saving} onclick={saveAi}>
		{aiState.saving ? $_('common.saving') : $_('common.save')}
	</button>
</section>
