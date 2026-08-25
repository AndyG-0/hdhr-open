<script lang="ts">
	import { api, type HDHomeRunTranscodePreset, type HWAccelDiagnostics } from '$lib/api';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { onMount } from 'svelte';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialSettings: Record<string, unknown> | null;
	}

	let { initialSettings }: Props = $props();

	let playbackModeInput = $state('server_transcode');
	let hwaccelInput = $state('software');
	let customFfmpegArgsInput = $state('');
	let hwaccelDeviceInput = $state('/dev/dri/renderD128');
	let ffmpegDebugInput = $state(false);
	let thumbnailsEnabledInput = $state(true);
	const playbackState = new SaveState();

	loadOnceWhen(
		() => initialSettings !== null,
		() => {
			playbackModeInput = (initialSettings!.playback_mode as string) ?? 'server_transcode';
			hwaccelInput = (initialSettings!.hwaccel as string) ?? 'software';
			customFfmpegArgsInput = (initialSettings!.custom_ffmpeg_args as string) ?? '';
			hwaccelDeviceInput = (initialSettings!.hwaccel_device as string) ?? '/dev/dri/renderD128';
			ffmpegDebugInput = (initialSettings!.ffmpeg_debug as boolean) ?? false;
			thumbnailsEnabledInput = (initialSettings!.thumbnails_enabled as boolean) ?? true;
		},
	);

	let transcodePresets = $state<HDHomeRunTranscodePreset[]>([]);
	const selectedPreset = $derived(transcodePresets.find((p) => p.id === hwaccelInput) ?? null);

	onMount(async () => {
		try {
			transcodePresets = await api.hdhomerunTranscodePresets();
		} catch {
			transcodePresets = [];
		}
	});

	// Word-splits the way Python's shlex.split does — which is what the
	// backend uses on custom_ffmpeg_args (transcoding._output_args). A plain
	// split(/\s+/) disagrees with it on any quoted argument (a filter graph
	// with spaces, a path with a space), so the preview would show a command
	// the backend never runs.
	function shlexSplit(input: string): string[] {
		const tokens: string[] = [];
		// A quoted run, an escaped char, or a run of unquoted non-space.
		const pattern = /"((?:\\.|[^"\\])*)"|'([^']*)'|((?:\\.|[^\s'"\\])+)/g;
		let token = '';
		let end = 0;
		for (const match of input.matchAll(pattern)) {
			// A gap since the previous match means whitespace, i.e. a token
			// boundary; adjacent matches ("-vf"x'y') are one token.
			if (match.index > end && token) {
				tokens.push(token);
				token = '';
			}
			const [, doubleQuoted, singleQuoted, bare] = match;
			if (singleQuoted !== undefined) token += singleQuoted;
			else token += (doubleQuoted ?? bare).replace(/\\(.)/g, '$1');
			end = match.index + match[0].length;
		}
		if (token) tokens.push(token);
		return tokens;
	}

	// Mirrors transcoding.build_ffmpeg_args()'s argument order, so the
	// command shown while editing matches what saving would actually run.
	const livePreviewCommand = $derived.by(() => {
		if (!selectedPreset) return '';
		let outputArgs = selectedPreset.output_args;
		if (hwaccelInput === 'custom') {
			const trimmed = customFfmpegArgsInput.trim();
			outputArgs = trimmed
				? shlexSplit(trimmed)
				: (transcodePresets.find((p) => p.id === 'software')?.output_args ?? []);
		}
		const device = hwaccelDeviceInput.trim() || '/dev/dri/renderD128';
		const substitute = (args: string[]) => args.map((arg) => arg.replaceAll('{device}', device));
		return [
			'ffmpeg',
			'-hide_banner',
			'-loglevel',
			ffmpegDebugInput ? 'verbose' : 'warning',
			'-nostats',
			...substitute(selectedPreset.input_args),
			'-i',
			'<channel stream>',
			...substitute(outputArgs),
			'-f',
			'mpegts',
			'pipe:1',
		].join(' ');
	});

	let diagnostics = $state<HWAccelDiagnostics | null>(null);
	let diagnosticsRunning = $state(false);
	let diagnosticsError = $state<string | null>(null);

	async function runDiagnostics() {
		diagnosticsRunning = true;
		diagnosticsError = null;
		try {
			diagnostics = await api.hdhomerunHwaccelDiagnostics(hwaccelDeviceInput.trim() || undefined);
		} catch {
			diagnostics = null;
			diagnosticsError = get(_)('hdhomerun.detail.diagnostics_failed');
		} finally {
			diagnosticsRunning = false;
		}
	}

	function playbackFormSettings(): Record<string, unknown> {
		return {
			playback_mode: playbackModeInput,
			hwaccel: hwaccelInput,
			custom_ffmpeg_args: customFfmpegArgsInput,
			hwaccel_device: hwaccelDeviceInput.trim(),
			ffmpeg_debug: ffmpegDebugInput,
			thumbnails_enabled: thumbnailsEnabledInput,
		};
	}

	async function savePlayback() {
		await playbackState.run(async () => {
			await api.updateNetworkIntegration('hdhomerun', playbackFormSettings());
		}, get(_)('common.connection_save_error'));
	}
</script>

<section>
	<h3>{$_('hdhomerun.detail.playback_heading')}</h3>
	<div class="auth-mode">
		<button
			type="button"
			class:active={playbackModeInput === 'server_transcode'}
			onclick={() => (playbackModeInput = 'server_transcode')}
		>
			{$_('hdhomerun.detail.mode_server_transcode')}
		</button>
		<button
			type="button"
			class:active={playbackModeInput === 'external'}
			onclick={() => (playbackModeInput = 'external')}
		>
			{$_('hdhomerun.detail.mode_external')}
		</button>
	</div>
	{#if playbackModeInput === 'server_transcode'}
		<p class="hint">{$_('hdhomerun.detail.server_transcode_hint')}</p>

		<label>
			{$_('hdhomerun.detail.transcode_hardware_label')}
			<select bind:value={hwaccelInput}>
				{#each transcodePresets as preset (preset.id)}
					<option value={preset.id}>{preset.label}</option>
				{/each}
			</select>
		</label>
		{#if selectedPreset}
			<p class="hint">{selectedPreset.description}</p>
		{/if}

		{#if hwaccelInput === 'custom'}
			<label>
				{$_('hdhomerun.detail.custom_ffmpeg_label')}
				<textarea bind:value={customFfmpegArgsInput} rows="2" placeholder="-c:v h264_v4l2m2m -b:v 4M -c:a aac"
				></textarea>
			</label>
		{/if}

		<label>
			{$_('hdhomerun.detail.hwaccel_device_label')}
			<input bind:value={hwaccelDeviceInput} placeholder="/dev/dri/renderD128" />
		</label>
		<p class="hint">{$_('hdhomerun.detail.hwaccel_device_hint')}</p>

		<label class="checkbox">
			<input type="checkbox" bind:checked={ffmpegDebugInput} />
			{$_('hdhomerun.detail.ffmpeg_debug_label')}
		</label>
		<p class="hint">{$_('hdhomerun.detail.ffmpeg_debug_hint')}</p>

		<label class="checkbox">
			<input type="checkbox" bind:checked={thumbnailsEnabledInput} />
			{$_('hdhomerun.detail.thumbnails_enabled_label')}
		</label>
		<p class="hint">{$_('hdhomerun.detail.thumbnails_enabled_hint')}</p>

		<p class="hint ffmpeg-command">
			<code>{livePreviewCommand}</code>
		</p>

		<div class="diagnostics">
			<h4>{$_('hdhomerun.detail.diagnostics_heading')}</h4>
			<p class="hint">{$_('hdhomerun.detail.diagnostics_hint')}</p>
			<button type="button" class="test" disabled={diagnosticsRunning} onclick={runDiagnostics}>
				{diagnosticsRunning ? $_('hdhomerun.detail.diagnostics_running') : $_('hdhomerun.detail.diagnostics_run')}
			</button>

			{#if diagnosticsError}
				<p class="hint error">{diagnosticsError}</p>
			{/if}

			{#if diagnostics}
				{#each diagnostics.summary as finding, index (index)}
					<p class="finding">{finding}</p>
				{/each}

				<h4>{$_('hdhomerun.detail.diagnostics_devices_heading')}</h4>
				{#if !diagnostics.dri.dir_exists}
					<p class="hint">{$_('hdhomerun.detail.diagnostics_no_dri')}</p>
				{:else if diagnostics.dri.devices.length === 0}
					<p class="hint">{$_('hdhomerun.detail.diagnostics_no_devices')}</p>
				{:else}
					<ul class="diagnostics-list">
						{#each diagnostics.dri.devices as device (device.path)}
							<li>
								<span class="status" class:ok={device.readable && device.writable}>
									{device.readable && device.writable ? '✓' : '✗'}
								</span>
								<code>{device.path}</code>
								<span class="muted">
									{device.error ?? `${device.mode} ${device.owner_uid}:${device.owner_gid}`}
								</span>
							</li>
						{/each}
					</ul>
				{/if}
				<p class="hint">
					{$_('hdhomerun.detail.diagnostics_process', {
						values: {
							uid: diagnostics.process.uid,
							gid: diagnostics.process.gid,
							groups: diagnostics.process.groups.join(', ') || '—',
						},
					})}
				</p>

				{#if diagnostics.vainfo}
					<h4>{$_('hdhomerun.detail.diagnostics_driver_heading')}</h4>
					<p class="hint">
						{diagnostics.vainfo.driver ?? $_('common.unknown')} ·
						{$_('hdhomerun.detail.diagnostics_h264_encode')}: {diagnostics.vainfo.can_encode_h264 ? '✓' : '✗'} ·
						{$_('hdhomerun.detail.diagnostics_mpeg2_decode')}: {diagnostics.vainfo.can_decode_mpeg2 ? '✓' : '✗'}
					</p>
					{#if !diagnostics.vainfo.ok}
						<pre class="diagnostics-output">{diagnostics.vainfo.output}</pre>
					{/if}
				{/if}

				<h4>{$_('hdhomerun.detail.diagnostics_presets_heading')}</h4>
				{#if diagnostics.sample_error}
					<p class="hint error">{diagnostics.sample_error}</p>
				{/if}
				<ul class="diagnostics-list">
					{#each Object.entries(diagnostics.probes) as [presetId, probe] (presetId)}
						<li>
							<span class="status" class:ok={probe.ok}>{probe.ok ? '✓' : '✗'}</span>
							<code>{presetId}</code>
							{#if !probe.ok}
								<pre class="diagnostics-output">{probe.output ||
										$_('hdhomerun.detail.diagnostics_no_output')}</pre>
							{/if}
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	{:else}
		<p class="hint">{$_('hdhomerun.detail.external_only_hint')}</p>
	{/if}

	{#if playbackState.error}
		<p class="hint error">{playbackState.error}</p>
	{/if}
	{#if playbackState.saved}
		<p class="hint">{$_('common.saved')}</p>
	{/if}

	<button class="save" disabled={playbackState.saving} onclick={savePlayback}>
		{playbackState.saving ? $_('common.saving') : $_('hdhomerun.detail.save_playback_settings')}
	</button>
</section>

<style>
	.auth-mode {
		display: flex;
		gap: 0.5rem;
	}

	.auth-mode button {
		flex: 1;
		background: none;
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.5rem;
		font-size: 0.85rem;
		color: var(--color-text-muted);
		cursor: pointer;
	}

	.auth-mode button.active {
		border-color: var(--color-accent);
		color: var(--color-accent);
	}

	label.checkbox {
		flex-direction: row;
		align-items: center;
		gap: 0.5rem;
	}

	.diagnostics {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		border-top: 1px solid var(--color-border);
		padding-top: 0.75rem;
		margin-top: 0.5rem;
	}

	.diagnostics h4 {
		margin: 0.5rem 0 0;
		font-size: 0.85rem;
		color: var(--color-text-muted);
	}

	.finding {
		margin: 0;
		font-size: 0.85rem;
	}

	.diagnostics-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		font-size: 0.85rem;
	}

	.diagnostics-list .status {
		color: var(--color-danger, #e05a5a);
		margin-right: 0.4rem;
	}

	.diagnostics-list .status.ok {
		color: var(--color-success, #4caf50);
	}

	.diagnostics-list .muted {
		color: var(--color-text-muted);
		margin-left: 0.4rem;
	}

	.diagnostics-output {
		margin: 0.25rem 0 0;
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		font-family: var(--font-mono, monospace);
		font-size: 0.75rem;
		max-height: 12rem;
		overflow: auto;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}

	.ffmpeg-command {
		margin: 0;
	}

	.ffmpeg-command code {
		display: block;
		overflow-x: auto;
		white-space: pre;
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		font-size: 0.8rem;
	}
</style>
