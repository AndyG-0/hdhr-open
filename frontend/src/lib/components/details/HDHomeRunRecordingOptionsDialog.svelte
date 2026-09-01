<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type {
		HDHomeRunGuideEntry,
		HDHomeRunRecordingRule,
		RecordingRuleOptions,
		HDHomeRunChannel,
	} from '$lib/api';

	interface Props {
		airing: HDHomeRunGuideEntry;
		channelName: string;
		channelNumber?: string;
		channels?: HDHomeRunChannel[];
		isHd?: boolean;
		canRecordSeries?: boolean;
		officialDvrActive?: boolean;
		loading?: boolean;
		existingRule?: HDHomeRunRecordingRule | null;
		onWatch?: () => void;
		onCancelRule?: (ruleId: string) => void;
		onConfirm: (mode: 'episode' | 'series', options: RecordingRuleOptions) => void;
		onClose: () => void;
	}

	let {
		airing,
		channelName,
		channelNumber = '',
		channels = [],
		isHd = false,
		canRecordSeries = false,
		officialDvrActive = false,
		loading = false,
		existingRule = null,
		onWatch,
		onCancelRule,
		onConfirm,
		onClose,
	}: Props = $props();

	let startPaddingMinutes = $state(0);
	let endPaddingMinutes = $state(0);
	let recentOnly = $state(false);
	let selectedServer = $state<'default' | 'builtin' | 'hdhomerun'>('default');
	let retentionMode = $state<'unlimited' | 'limited'>('unlimited');
	let retentionCount = $state(3);
	let titleMatchMode = $state<'exact' | 'contains'>('exact');
	let keywordQuery = $state('');
	let channelMode = $state<'any' | 'current' | 'custom'>('current');
	let selectedCustomChannels = $state<string[]>([]);
	let imageFailed = $state(false);

	const effectiveChannelNumber = $derived(channelNumber || airing.channel_number || '');
	const effectiveIsHd = $derived(isHd || airing.is_hd || false);
	const nowSeconds = Math.floor(Date.now() / 1000);
	const isLive = $derived(
		airing.start != null && airing.end != null && airing.start <= nowSeconds && nowSeconds < airing.end,
	);

	$effect(() => {
		const initialCh = effectiveChannelNumber;
		if (initialCh && selectedCustomChannels.length === 0) {
			selectedCustomChannels = [initialCh];
		}
	});

	const isKeywordActive = $derived(keywordQuery.trim().length > 0 || titleMatchMode === 'contains');
	const isOfficialDvrTarget = $derived(
		!isKeywordActive && (selectedServer === 'hdhomerun' || (selectedServer === 'default' && officialDvrActive)),
	);

	function getEffectiveChannel(): string | undefined {
		if (channelMode === 'any') return undefined;
		if (channelMode === 'current') return effectiveChannelNumber || undefined;
		if (channelMode === 'custom') {
			const selected = selectedCustomChannels.filter(Boolean);
			return selected.length > 0 ? selected.join('|') : undefined;
		}
		return undefined;
	}

	function buildOptions(): RecordingRuleOptions {
		const trimmedKeywords = keywordQuery.trim();
		const hasKeywords = trimmedKeywords.length > 0;
		const hasContainsMatch = titleMatchMode === 'contains';
		const serverToUse = (hasKeywords || hasContainsMatch)
			? 'builtin'
			: (selectedServer !== 'default' ? selectedServer : undefined);

		return {
			title: airing.title,
			titleMatchMode: hasContainsMatch ? 'contains' : 'exact',
			keywordQuery: hasKeywords ? trimmedKeywords : undefined,
			channel: getEffectiveChannel(),
			startPadding: startPaddingMinutes ? startPaddingMinutes * 60 : undefined,
			endPadding: endPaddingMinutes ? endPaddingMinutes * 60 : undefined,
			recentOnly: recentOnly || undefined,
			maxEpisodesToKeep:
				!isOfficialDvrTarget && retentionMode === 'limited' && retentionCount > 0
					? retentionCount
					: undefined,
			server: serverToUse,
		};
	}

	let dialogEl = $state<HTMLDivElement | null>(null);

	function handleWindowPointerDown(e: PointerEvent) {
		if (dialogEl && e.target instanceof Node && !dialogEl.contains(e.target)) onClose();
	}

	function handleWindowKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}

	function formatTime(seconds: number | null): string {
		if (seconds === null) return '';
		return new Date(seconds * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	}

	function formatTimeSpan(start: number | null, end: number | null): string {
		if (start === null) return '';
		const startDate = new Date(start * 1000);
		const startOfToday = new Date();
		startOfToday.setHours(0, 0, 0, 0);
		const diffDays = Math.round((startDate.getTime() - startOfToday.getTime()) / (86400 * 1000));

		let dayStr = '';
		if (diffDays === 0) {
			dayStr = $_('hdhomerun.detail.guide_today');
		} else if (diffDays === 1) {
			dayStr = $_('hdhomerun.detail.guide_tomorrow');
		} else {
			dayStr = startDate.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
		}

		const timeSpan = formatTime(start) + (end !== null ? ` – ${formatTime(end)}` : '');
		const durationMin = end !== null && start !== null ? Math.round((end - start) / 60) : null;
		const durationStr = durationMin ? ` (${durationMin} min)` : '';
		return `${dayStr} · ${timeSpan}${durationStr}`;
	}

	function formatEpisodeHeader(airing: HDHomeRunGuideEntry): string {
		const parts: string[] = [];
		if (airing.season_number && airing.episode_number) {
			const epNum = airing.episode_number.includes('.')
				? airing.episode_number.split('.')[1]
				: airing.episode_number;
			parts.push(`S${airing.season_number}E${epNum}`);
		} else if (airing.episode_number) {
			if (airing.episode_number.includes('.')) {
				const [s, e] = airing.episode_number.split('.');
				parts.push(`S${s}E${e}`);
			} else {
				parts.push(`Ep ${airing.episode_number}`);
			}
		}
		if (airing.episode_title) {
			parts.push(airing.episode_title);
		}
		return parts.join(' • ');
	}

	function formatOriginalAirDate(val: number | string | null | undefined): string | null {
		if (!val) return null;
		if (typeof val === 'number') {
			return new Date(val * 1000).toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
		}
		if (typeof val === 'string' && /^\d{4}-\d{2}-\d{2}/.test(val)) {
			const [y, m, d] = val.split('T')[0].split('-').map(Number);
			const localDate = new Date(y, m - 1, d);
			return localDate.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
		}
		const d = new Date(val);
		if (isNaN(d.getTime())) return String(val);
		return d.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
	}

	function formatAudio(audio: string): string {
		const lower = audio.toLowerCase().trim();
		if (lower === 'stereo') return 'STEREO';
		if (lower.includes('5.1')) return '5.1 SURROUND';
		if (lower.includes('dolby') || lower.includes('dd')) return 'DOLBY';
		if (lower === 'mono') return 'MONO';
		return audio.toUpperCase();
	}
</script>

<svelte:window onpointerdown={handleWindowPointerDown} onkeydown={handleWindowKeydown} />

<div class="options-backdrop" onclick={onClose} onkeydown={(e) => e.key === 'Escape' && onClose()} role="presentation"></div>
<div
	class="options-dialog"
	bind:this={dialogEl}
	role="dialog"
	aria-label={$_('hdhomerun.detail.recording_options_title')}
>
	<div class="dialog-header">
		<div class="channel-chip">
			{#if channelNumber}
				<span class="chip-number">{channelNumber}</span>
			{/if}
			{#if channelName}
				<span class="chip-name">{channelName}</span>
			{/if}
			{#if effectiveIsHd}
				<span class="badge hd-badge">HD</span>
			{/if}
		</div>
		<button class="options-close" onclick={onClose} aria-label={$_('common.close')}>✕</button>
	</div>

	{#if airing.image_url && !imageFailed}
		<div class="hero-image-wrap">
			<img
				src={airing.image_url}
				alt={airing.title}
				class="hero-image"
				onerror={() => (imageFailed = true)}
			/>
		</div>
	{/if}

	<div class="program-meta-section">
		<h2 class="program-title">{airing.title}</h2>

		{#if formatEpisodeHeader(airing)}
			<div class="program-episode">{formatEpisodeHeader(airing)}</div>
		{/if}

		<div class="badges-row">
			{#if isLive}
				<span class="badge live-badge">{$_('hdhomerun.detail.live_badge')}</span>
			{/if}
			{#if airing.is_new}
				<span class="badge new-badge">{$_('hdhomerun.detail.new_badge')}</span>
			{/if}
			{#if effectiveIsHd}
				<span class="badge feature-badge">HD</span>
			{/if}
			{#if airing.has_cc !== false}
				<span class="badge feature-badge">CC</span>
			{/if}
			{#if airing.audio}
				<span class="badge feature-badge">{formatAudio(airing.audio)}</span>
			{/if}
			{#if airing.category}
				{#each airing.category.split(',').map((c) => c.trim()).filter(Boolean) as cat}
					<span class="badge category-badge">{cat}</span>
				{/each}
			{/if}
		</div>

		{#if airing.start != null}
			<div class="time-row">
				<span class="time-icon">🕒</span>
				<span class="time-text">{formatTimeSpan(airing.start, airing.end)}</span>
			</div>
		{/if}

		{#if formatOriginalAirDate(airing.original_airdate)}
			<div class="airdate-row">
				{$_('hdhomerun.detail.original_air_date', {
					values: { date: formatOriginalAirDate(airing.original_airdate) },
				})}
			</div>
		{/if}

		{#if airing.synopsis}
			<p class="synopsis-text">{airing.synopsis}</p>
		{/if}
	</div>

	<div class="recording-settings-panel">
		<div class="panel-header">
			<span class="panel-title">{$_('hdhomerun.detail.recording_options_section')}</span>
		</div>

		<div class="options-body">
			<label>
				{$_('hdhomerun.detail.server_label')}
				<select bind:value={selectedServer} aria-label={$_('hdhomerun.detail.server_label')}>
					<option value="default">{$_('hdhomerun.detail.server_default')}</option>
					<option value="builtin">{$_('hdhomerun.detail.server_builtin')}</option>
					<option value="hdhomerun">{$_('hdhomerun.detail.server_hdhomerun')}</option>
				</select>
			</label>

			<div class="match-mode-field">
				<span class="match-mode-label">{$_('hdhomerun.detail.keyword_rule_match_mode_label')}</span>
				<div class="match-mode-choices">
					<label class="radio">
						<input type="radio" name="title-match-mode" value="exact" bind:group={titleMatchMode} />
						{$_('hdhomerun.detail.keyword_rule_match_exact')}
					</label>
					<label class="radio">
						<input type="radio" name="title-match-mode" value="contains" bind:group={titleMatchMode} />
						{$_('hdhomerun.detail.keyword_rule_match_contains')}
					</label>
				</div>
			</div>

			<div class="keyword-field">
				<label>
					{$_('hdhomerun.detail.keyword_rule_keyword_label')}
					<input
						type="text"
						bind:value={keywordQuery}
						placeholder={$_('hdhomerun.detail.keyword_rule_keyword_placeholder')}
					/>
				</label>
				{#if airing.episode_title && !keywordQuery.toLowerCase().includes(airing.episode_title.toLowerCase())}
					<button
						type="button"
						class="keyword-suggestion-chip"
						onclick={() => {
							if (!keywordQuery.trim()) {
								keywordQuery = airing.episode_title!;
							} else {
								keywordQuery = `${keywordQuery.trim()}, ${airing.episode_title}`;
							}
						}}
					>
						+ {$_('hdhomerun.detail.use_subtitle_as_keyword', { values: { subtitle: airing.episode_title } })}
					</button>
				{/if}
				<span class="hint">{$_('hdhomerun.detail.keyword_rule_keyword_hint')}</span>
			</div>

			{#if isKeywordActive}
				<div class="keyword-server-note">
					ℹ️ {$_('hdhomerun.detail.keyword_rule_builtin_only_note')}
				</div>
			{/if}

			<div class="channel-scope-field">
				<span class="channel-scope-label">{$_('hdhomerun.detail.channel_label')}</span>
				<div class="channel-scope-choices">
					{#if effectiveChannelNumber}
						<label class="radio">
							<input type="radio" name="channel-mode" value="current" bind:group={channelMode} />
							{$_('hdhomerun.detail.channel_mode_current', { values: { channel: `${effectiveChannelNumber} ${channelName}`.trim() } })}
						</label>
					{/if}
					<label class="radio">
						<input type="radio" name="channel-mode" value="any" bind:group={channelMode} />
						{$_('hdhomerun.detail.channel_mode_any')}
					</label>
					{#if channels && channels.length > 0}
						<label class="radio">
							<input type="radio" name="channel-mode" value="custom" bind:group={channelMode} />
							{$_('hdhomerun.detail.channel_mode_custom')}
						</label>
					{/if}
				</div>

				{#if channelMode === 'custom' && channels && channels.length > 0}
					<div class="channel-picker-wrap">
						<span class="channel-picker-prompt">{$_('hdhomerun.detail.select_channels_prompt')}</span>
						<div class="channel-checklist" role="group" aria-label={$_('hdhomerun.detail.select_channels_prompt')}>
							{#each channels as ch}
								<label class="channel-check-item">
									<input
										type="checkbox"
										value={ch.channel_number}
										checked={selectedCustomChannels.includes(ch.channel_number)}
										onchange={(e) => {
											const checked = (e.currentTarget as HTMLInputElement).checked;
											if (checked) {
												if (!selectedCustomChannels.includes(ch.channel_number)) {
													selectedCustomChannels = [...selectedCustomChannels, ch.channel_number];
												}
											} else {
												selectedCustomChannels = selectedCustomChannels.filter((c) => c !== ch.channel_number);
											}
										}}
									/>
									<span class="channel-check-number">{ch.channel_number}</span>
									<span class="channel-check-name">{ch.name}</span>
								</label>
							{/each}
						</div>
					</div>
				{/if}
			</div>

			<div class="padding-grid">
				<label>
					{$_('hdhomerun.detail.start_padding_label')}
					<input type="number" min="0" step="1" bind:value={startPaddingMinutes} />
				</label>

				<label>
					{$_('hdhomerun.detail.end_padding_label')}
					<input type="number" min="0" step="1" bind:value={endPaddingMinutes} />
				</label>
			</div>

			<label class="checkbox">
				<input type="checkbox" bind:checked={recentOnly} />
				{$_('hdhomerun.detail.new_episodes_only_label')}
			</label>

			{#if isOfficialDvrTarget}
				<p class="hint">{$_('hdhomerun.detail.retention_official_dvr_note')}</p>
			{:else}
				<div class="retention-field">
					<span class="retention-label">{$_('hdhomerun.detail.retention_label')}</span>
					<div class="retention-choices">
						<label class="radio">
							<input type="radio" name="retention-mode" value="unlimited" bind:group={retentionMode} />
							{$_('hdhomerun.detail.retention_unlimited')}
						</label>
						<label class="radio">
							<input type="radio" name="retention-mode" value="limited" bind:group={retentionMode} />
							{$_('hdhomerun.detail.retention_keep_last', { values: { count: retentionCount } })}
						</label>
					</div>
					{#if retentionMode === 'limited'}
						<input
							type="number"
							min="1"
							step="1"
							class="retention-count"
							bind:value={retentionCount}
							aria-label={$_('hdhomerun.detail.retention_label')}
						/>
					{/if}
				</div>
			{/if}
		</div>
	</div>

	<div class="options-footer">
		{#if isLive && onWatch}
			<button class="options-button watch" onclick={() => { onWatch?.(); onClose(); }}>
				{$_('hdhomerun.detail.watch_button')}
			</button>
		{/if}

		{#if existingRule && onCancelRule}
			<button
				class="options-button danger"
				disabled={loading}
				onclick={() => { onCancelRule?.(existingRule.RecordingRuleID); onClose(); }}
			>
				{$_('hdhomerun.detail.cancel_recording')}
			</button>
		{:else}
			<button
				class="options-button record"
				disabled={loading}
				onclick={() => onConfirm('episode', buildOptions())}
			>
				🔴 {$_('hdhomerun.detail.record_episode')}
			</button>
			{#if canRecordSeries}
				<button
					class="options-button primary"
					disabled={loading}
					onclick={() => onConfirm('series', buildOptions())}
				>
					{#if isKeywordActive}
						{$_('hdhomerun.detail.record_series_with_keywords')}
					{:else}
						{$_('hdhomerun.detail.record_series')}
					{/if}
				</button>
			{/if}
		{/if}
	</div>
</div>

<style>
	.options-backdrop {
		position: fixed;
		inset: 0;
		z-index: 60;
		background: rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(4px);
	}

	.options-dialog {
		position: fixed;
		z-index: 61;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		width: min(30rem, calc(100vw - 2rem));
		max-height: calc(100vh - 2.5rem);
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.85rem;
		box-shadow: 0 1rem 3rem rgba(0, 0, 0, 0.45);
		padding: 1.25rem;
		gap: 1rem;
	}

	.dialog-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.channel-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: 0.4rem;
		padding: 0.25rem 0.55rem;
		font-size: 0.82rem;
	}

	.chip-number {
		font-weight: 700;
		color: var(--color-accent);
	}

	.chip-name {
		color: var(--color-text-muted);
		font-weight: 500;
	}

	.options-close {
		background: none;
		border: none;
		color: var(--color-text-muted);
		font-size: 1.1rem;
		cursor: pointer;
		padding: 0.2rem 0.4rem;
		border-radius: 0.3rem;
		transition: color 0.15s ease, background 0.15s ease;
	}

	.options-close:hover {
		color: var(--color-text);
		background: var(--color-surface-hover);
	}

	.hero-image-wrap {
		width: 100%;
		max-height: 180px;
		overflow: hidden;
		border-radius: 0.6rem;
		background: var(--color-bg);
		border: 1px solid var(--color-border);
	}

	.hero-image {
		width: 100%;
		height: 100%;
		max-height: 180px;
		object-fit: cover;
		display: block;
	}

	.program-meta-section {
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}

	.program-title {
		margin: 0;
		font-size: 1.25rem;
		font-weight: 700;
		line-height: 1.25;
		color: var(--color-text);
	}

	.program-episode {
		font-size: 0.92rem;
		font-weight: 600;
		color: var(--color-warning, #d9a441);
	}

	.badges-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		align-items: center;
		margin-top: 0.15rem;
	}

	.badge {
		font-size: 0.7rem;
		font-weight: 700;
		padding: 0.15rem 0.4rem;
		border-radius: 0.25rem;
		letter-spacing: 0.02em;
		text-transform: uppercase;
	}

	.hd-badge,
	.feature-badge {
		background: rgba(91, 141, 250, 0.15);
		color: var(--color-accent);
		border: 1px solid rgba(91, 141, 250, 0.35);
	}

	.live-badge {
		background: var(--color-error);
		color: #fff;
	}

	.new-badge {
		background: rgba(76, 175, 125, 0.18);
		color: var(--color-success);
		border: 1px solid rgba(76, 175, 125, 0.35);
	}

	.category-badge {
		background: var(--color-bg);
		color: var(--color-text-muted);
		border: 1px solid var(--color-border);
		text-transform: none;
		font-weight: 500;
	}

	.time-row {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.84rem;
		color: var(--color-text-muted);
		margin-top: 0.2rem;
	}

	.time-icon {
		font-size: 0.85rem;
	}

	.airdate-row {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.synopsis-text {
		margin: 0.35rem 0 0;
		font-size: 0.86rem;
		line-height: 1.45;
		color: var(--color-text);
		white-space: pre-wrap;
	}

	.recording-settings-panel {
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: 0.6rem;
		padding: 0.75rem;
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}

	.panel-title {
		font-size: 0.82rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-text-muted);
	}

	.options-body {
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
	}

	.options-body label {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: 0.84rem;
		color: var(--color-text);
	}

	.padding-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 0.6rem;
	}

	.options-body select,
	.options-body input[type='number'],
	.options-body input[type='text'] {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.35rem;
		padding: 0.4rem 0.5rem;
		color: var(--color-text);
		font-size: 0.84rem;
	}

	.options-body select:focus,
	.options-body input[type='number']:focus,
	.options-body input[type='text']:focus {
		outline: none;
		border-color: var(--color-accent);
	}

	.match-mode-field,
	.keyword-field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.match-mode-label {
		font-size: 0.84rem;
		color: var(--color-text);
	}

	.match-mode-choices {
		display: flex;
		gap: 1rem;
		align-items: center;
	}

	.keyword-suggestion-chip {
		display: inline-flex;
		align-self: flex-start;
		background: rgba(91, 141, 250, 0.12);
		border: 1px dashed rgba(91, 141, 250, 0.4);
		border-radius: 0.35rem;
		padding: 0.25rem 0.55rem;
		font-size: 0.78rem;
		color: var(--color-accent);
		cursor: pointer;
		transition: background 0.15s ease;
		text-align: left;
	}

	.keyword-suggestion-chip:hover {
		background: rgba(91, 141, 250, 0.22);
	}

	.keyword-server-note {
		font-size: 0.78rem;
		color: var(--color-accent);
		background: rgba(91, 141, 250, 0.08);
		border: 1px solid rgba(91, 141, 250, 0.25);
		border-radius: 0.35rem;
		padding: 0.35rem 0.55rem;
		line-height: 1.35;
	}

	.channel-scope-field {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.channel-scope-label {
		font-size: 0.84rem;
		color: var(--color-text);
	}

	.channel-scope-choices {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.channel-picker-wrap {
		margin-top: 0.25rem;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		background: rgba(0, 0, 0, 0.15);
		border: 1px solid var(--color-border);
		border-radius: 0.4rem;
		padding: 0.5rem;
	}

	.channel-picker-prompt {
		font-size: 0.78rem;
		color: var(--color-text-muted);
	}

	.channel-checklist {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		gap: 0.35rem;
		max-height: 9rem;
		overflow-y: auto;
		padding: 0.2rem 0;
	}

	.channel-check-item {
		display: flex !important;
		flex-direction: row !important;
		align-items: center;
		gap: 0.35rem !important;
		font-size: 0.8rem !important;
		cursor: pointer;
		padding: 0.2rem 0.3rem;
		border-radius: 0.25rem;
	}

	.channel-check-item:hover {
		background: rgba(255, 255, 255, 0.05);
	}

	.channel-check-number {
		font-weight: 600;
	}

	.channel-check-name {
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.options-body label.checkbox,
	.options-body label.radio {
		flex-direction: row;
		align-items: center;
		gap: 0.4rem;
	}

	.hint {
		font-size: 0.78rem;
		color: var(--color-text-muted);
		margin: 0;
	}

	.retention-field {
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.retention-label {
		font-size: 0.84rem;
		color: var(--color-text);
	}

	.retention-choices {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.retention-choices .radio {
		font-size: 0.84rem;
	}

	.retention-count {
		width: 5rem;
	}

	.options-footer {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 0.5rem;
		margin-top: 0.25rem;
	}

	.options-button {
		background: var(--color-surface-hover, rgba(0, 0, 0, 0.05));
		border: 1px solid var(--color-border);
		border-radius: 0.4rem;
		padding: 0.5rem 0.9rem;
		font-size: 0.85rem;
		font-weight: 500;
		color: var(--color-text);
		cursor: pointer;
		transition: background 0.15s ease, border-color 0.15s ease;
	}

	.options-button:hover:not(:disabled) {
		background: var(--color-border);
	}

	.options-button:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.options-button.watch {
		background: var(--color-accent);
		border-color: var(--color-accent);
		color: var(--color-on-accent, #fff);
	}

	.options-button.primary {
		background: var(--color-accent);
		border-color: var(--color-accent);
		color: var(--color-on-accent, #fff);
	}

	.options-button.danger {
		background: rgba(224, 90, 90, 0.15);
		border-color: var(--color-error);
		color: var(--color-error);
	}

	.options-button.danger:hover:not(:disabled) {
		background: var(--color-error);
		color: #fff;
	}
</style>
