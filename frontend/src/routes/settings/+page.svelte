<script lang="ts">
	import { api, type AppSettings, type XMLTVFeedChannel, type SchedulesDirectStation } from '$lib/api';

	import { user } from '$lib/stores/user';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';
	import PriorityList from '$lib/components/settings/PriorityList.svelte';
	import TmdbSection from '$lib/components/settings/TmdbSection.svelte';
	import AISettingsSection from '$lib/components/settings/AISettingsSection.svelte';
	import HouseholdMembersSection from '$lib/components/settings/HouseholdMembersSection.svelte';
	import ProfileSection from '$lib/components/settings/ProfileSection.svelte';
	import LanguageSection from '$lib/components/settings/LanguageSection.svelte';
	import AppearanceSection from '$lib/components/settings/AppearanceSection.svelte';
	import TimezoneSection from '$lib/components/settings/TimezoneSection.svelte';
	import SportsExtensionSection from '$lib/components/settings/SportsExtensionSection.svelte';
	import HDHomeRunNetworkSection from '$lib/components/settings/HDHomeRunNetworkSection.svelte';
	import PlaybackSection from '$lib/components/settings/PlaybackSection.svelte';
	import XmltvFeedSection from '$lib/components/settings/XmltvFeedSection.svelte';
	import SchedulesDirectSection from '$lib/components/settings/SchedulesDirectSection.svelte';
	import ChannelLineupSection from '$lib/components/settings/ChannelLineupSection.svelte';
	import JobsSection from '$lib/components/settings/JobsSection.svelte';

	let settings = $state<AppSettings | null>(null);
	let error = $state<string | null>(null);

	// /api/settings is admin-only — load it lazily once $user is known to be
	// an admin, so a member never fires a request that's guaranteed to 403.
	loadOnceWhen(() => $user?.role === 'admin', loadSettings);

	const VALID_GUIDE_PROVIDERS = ['xmltv', 'schedules_direct', 'hdhomerun_cloud'] as const;
	type GuideProviderId = (typeof VALID_GUIDE_PROVIDERS)[number];

	let guidePriorityList = $state<GuideProviderId[]>(['xmltv', 'schedules_direct', 'hdhomerun_cloud']);
	const guidePriorityState = new SaveState();

	const VALID_DVR_SERVERS = ['builtin', 'hdhomerun'] as const;
	type DvrServerId = (typeof VALID_DVR_SERVERS)[number];

	let dvrPriorityList = $state<DvrServerId[]>(['builtin', 'hdhomerun']);
	const dvrPriorityState = new SaveState();

	function parseGuidePriority(raw: string | undefined): GuideProviderId[] {
		const items = (raw ?? '')
			.split(',')
			.map((s) => s.trim())
			.filter((s): s is GuideProviderId => VALID_GUIDE_PROVIDERS.includes(s as GuideProviderId));
		for (const p of VALID_GUIDE_PROVIDERS) {
			if (!items.includes(p)) items.push(p);
		}
		return items;
	}

	function reorderGuidePriority(next: GuideProviderId[]) {
		guidePriorityList = next;
		guidePriorityState.saved = false;
	}

	function providerLabel(id: GuideProviderId): string {
		switch (id) {
			case 'xmltv':
				return get(_)('network_settings.guide_provider_xmltv');
			case 'schedules_direct':
				return get(_)('network_settings.guide_provider_schedules_direct');
			case 'hdhomerun_cloud':
				return get(_)('network_settings.guide_provider_hdhomerun');
		}
	}

	function providerSubLabel(id: GuideProviderId): string {
		switch (id) {
			case 'xmltv':
				return get(_)('network_settings.section_xmltv');
			case 'schedules_direct':
				return get(_)('network_settings.section_schedules_direct');
			case 'hdhomerun_cloud':
				return get(_)('network_settings.section_hdhomerun');
		}
	}

	function parseDvrPriority(raw: string | undefined): DvrServerId[] {
		const items = (raw ?? '')
			.split(',')
			.map((s) => s.trim())
			.filter((s): s is DvrServerId => VALID_DVR_SERVERS.includes(s as DvrServerId));
		for (const s of VALID_DVR_SERVERS) {
			if (!items.includes(s)) items.push(s);
		}
		return items;
	}

	function reorderDvrPriority(next: DvrServerId[]) {
		dvrPriorityList = next;
		dvrPriorityState.saved = false;
	}

	function dvrServerLabel(id: DvrServerId): string {
		switch (id) {
			case 'builtin':
				return get(_)('network_settings.dvr_provider_builtin');
			case 'hdhomerun':
				return get(_)('network_settings.dvr_provider_hdhomerun');
		}
	}

	function dvrServerDesc(id: DvrServerId): string {
		switch (id) {
			case 'builtin':
				return get(_)('network_settings.dvr_provider_builtin_desc');
			case 'hdhomerun':
				return get(_)('network_settings.dvr_provider_hdhomerun_desc');
		}
	}

	async function loadSettings() {
		try {
			settings = await api.settings();
			guidePriorityList = parseGuidePriority(settings.guide_provider_priority);
			dvrPriorityList = parseDvrPriority(settings.dvr_server_priority);
		} catch {
			error = 'Could not load settings.';
		}
	}

	// HDHomeRun network settings (tuner/DVR connection + optional XMLTV guide
	// URL) — same admin-only load-gate pattern as loadSettings() above,
	// since /api/network-settings writes (and this page's reads) are
	// admin-only.
	let hdhomerunNetworkSettings = $state<Record<string, unknown> | null>(null);

	// XMLTV guide feed — a separate network integration from the HDHomeRun
	// tuner/DVR connection above, so it has its own load/save flow against
	// the 'xmltv' network-integration type. Owned by XmltvFeedSection; only
	// the initial seed and the cross-cutting xmltvFeedChannels array (also
	// read by ChannelLineupSection) stay lifted here.
	let xmltvInitialUrl = $state<string | null>(null);
	let xmltvFeedChannels = $state<XMLTVFeedChannel[]>([]);

	// Schedules Direct settings — owned by SchedulesDirectSection; only the
	// initial seed and the cross-cutting sdStations array (also read by
	// ChannelLineupSection) stay lifted here.
	let sdInitialUsername = $state<string | null>(null);
	let sdInitialHasPassword = $state<boolean | null>(null);
	let sdStations = $state<SchedulesDirectStation[]>([]);

	// TMDB settings — seeded via loadNetworkIntegrations() below, owned by TmdbSection
	let tmdbInitialHasApiKey = $state<boolean | null>(null);

	// AI assistant settings — seeded via loadNetworkIntegrations() below, owned by AISettingsSection
	let aiInitialSettings = $state<Record<string, unknown> | null>(null);

	loadOnceWhen(() => $user?.role === 'admin', loadNetworkIntegrations);

	async function loadNetworkIntegrations() {
		try {
			const rows = await api.listNetworkIntegrations();

			const hdhomerun = rows.find((r) => r.type === 'hdhomerun');
			hdhomerunNetworkSettings = hdhomerun?.settings ?? {};

			const xmltv = rows.find((r) => r.type === 'xmltv');
			xmltvInitialUrl = (xmltv?.settings.url as string) ?? '';

			const sd = rows.find((r) => r.type === 'schedules_direct');
			sdInitialUsername = (sd?.settings.username as string) ?? '';
			sdInitialHasPassword = Boolean(sd?.settings.has_password);

			const tmdb = rows.find((r) => r.type === 'tmdb');
			tmdbInitialHasApiKey = Boolean(tmdb?.settings.has_api_key);

			const ai = rows.find((r) => r.type === 'ai');
			aiInitialSettings = ai?.settings ?? {};
		} catch {
			error = 'Could not load network settings.';
		}
	}

	async function saveGuidePriority() {
		await guidePriorityState.run(async () => {
			const priorityStr = guidePriorityList.join(',');
			settings = await api.updateSettings({ guide_provider_priority: priorityStr });
		}, get(_)('network_settings.guide_priority_error'));
	}

	async function saveDvrPriority() {
		await dvrPriorityState.run(async () => {
			const priorityStr = dvrPriorityList.join(',');
			settings = await api.updateSettings({ dvr_server_priority: priorityStr });
		}, get(_)('network_settings.dvr_priority_error'));
	}
</script>

<div class="settings-page">
	<h1>{$_('settings.page.title')}</h1>

	<div class="settings-group">
		<h2 class="group-title">{$_('settings.your_settings.title')}</h2>
		<p class="group-subtitle">{$_('settings.your_settings.subtitle')}</p>

		<ProfileSection />

		<LanguageSection />

		<AppearanceSection />
	</div>

	{#if $user?.role === 'admin'}
		<div class="settings-group">
			<h2 class="group-title">Admin settings</h2>
			<p class="group-subtitle">Shared across the whole household — visible only to admins.</p>

			<HouseholdMembersSection />

			{#if !settings}
				<p class="hint">{error ?? 'Loading…'}</p>
			{:else}
				<TimezoneSection initialTimezone={settings.timezone} />
			{/if}

			<HDHomeRunNetworkSection initialSettings={hdhomerunNetworkSettings} />

			<XmltvFeedSection initialUrl={xmltvInitialUrl} onFeedChannelsChanged={(fc) => (xmltvFeedChannels = fc)} />

			<SchedulesDirectSection
				initialUsername={sdInitialUsername}
				initialHasPassword={sdInitialHasPassword}
				onStationsChanged={(st) => (sdStations = st)}
			/>

			<TmdbSection initialHasApiKey={tmdbInitialHasApiKey} />

			<AISettingsSection initialSettings={aiInitialSettings} />

			<PriorityList
				heading={$_('network_settings.guide_priority_heading')}
				hint={$_('network_settings.guide_priority_hint')}
				items={guidePriorityList}
				onReorder={reorderGuidePriority}
				itemLabel={providerLabel}
				itemSubLabel={providerSubLabel}
				moveUpLabel={$_('network_settings.guide_priority_move_up')}
				moveDownLabel={$_('network_settings.guide_priority_move_down')}
				saving={guidePriorityState.saving}
				saved={guidePriorityState.saved}
				error={guidePriorityState.error}
				savedLabel={$_('network_settings.guide_priority_saved')}
				saveLabel={$_('network_settings.guide_priority_save')}
				savingLabel={$_('network_settings.guide_priority_saving')}
				onSave={saveGuidePriority}
			/>

			<PriorityList
				heading={$_('network_settings.dvr_priority_heading')}
				hint={$_('network_settings.dvr_priority_hint')}
				items={dvrPriorityList}
				onReorder={reorderDvrPriority}
				itemLabel={dvrServerLabel}
				itemSubLabel={dvrServerDesc}
				moveUpLabel={$_('network_settings.dvr_priority_move_up')}
				moveDownLabel={$_('network_settings.dvr_priority_move_down')}
				saving={dvrPriorityState.saving}
				saved={dvrPriorityState.saved}
				error={dvrPriorityState.error}
				savedLabel={$_('network_settings.dvr_priority_saved')}
				saveLabel={$_('network_settings.dvr_priority_save')}
				savingLabel={$_('network_settings.dvr_priority_saving')}
				onSave={saveDvrPriority}
			/>

			<PlaybackSection initialSettings={hdhomerunNetworkSettings} />

			<SportsExtensionSection
				initialEnabled={settings?.sports_extension_enabled ?? null}
				initialMaxMinutes={settings?.sports_extension_max_minutes ?? null}
			/>

			<JobsSection />

			<ChannelLineupSection
				{xmltvFeedChannels}
				{sdStations}
				onFeedChannelsChanged={(fc) => (xmltvFeedChannels = fc)}
				onStationsChanged={(st) => (sdStations = st)}
			/>
		</div>
	{/if}
</div>

<style>
	.settings-page {
		padding: 2rem;
		min-height: 100vh;
		max-width: 90rem;
		margin: 0 auto;
	}

	h1 {
		margin: 0 0 1.5rem;
	}

	:global(section) {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		margin-bottom: 1.25rem;
		break-inside: avoid;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.75rem;
		padding: 1rem;
	}

	:global(section h3) {
		margin: 0;
		font-size: 1rem;
	}

	:global(section h4) {
		margin: 0.5rem 0 0;
		font-size: 0.9rem;
	}

	:global(section h4:first-of-type) {
		margin-top: 0;
	}

	:global(.optional) {
		font-weight: normal;
		color: var(--color-text-muted);
		font-size: 0.85rem;
	}

	:global(.test-row) {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	:global(.test) {
		align-self: flex-start;
		background: none;
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.5rem 1rem;
		color: var(--color-accent);
		cursor: pointer;
	}

	:global(.test-result) {
		font-size: 0.85rem;
	}

	:global(.test-result.ok) {
		color: var(--color-success);
	}

	:global(.test-result.fail) {
		color: var(--color-error);
	}

	.settings-group {
		column-width: 22rem;
		column-gap: 1.25rem;
		margin-bottom: 2rem;
	}

	.group-title,
	.group-subtitle {
		column-span: all;
	}

	.group-title {
		margin: 0 0 0.25rem;
		font-size: 1.2rem;
	}

	.group-subtitle {
		margin: 0 0 1rem;
		color: var(--color-text-muted);
		font-size: 0.85rem;
	}

	:global(.channel-lineup-section) {
		column-span: all;
	}

	:global(label) {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		font-size: 0.9rem;
		color: var(--color-text-muted);
	}

	:global(input),
	:global(select),
	:global(textarea) {
		font: inherit;
		padding: 0.5rem 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-text);
	}

	:global(textarea) {
		font-family: var(--font-mono, monospace);
		font-size: 0.85rem;
		resize: vertical;
	}

	:global(.clear) {
		align-self: flex-start;
		background: none;
		border: none;
		color: var(--color-text-muted);
		text-decoration: underline;
		cursor: pointer;
		padding: 0;
		font-size: 0.85rem;
	}

	:global(.save) {
		align-self: flex-start;
		background: var(--color-accent);
		color: var(--color-surface);
		border: none;
		border-radius: 0.5rem;
		padding: 0.5rem 1rem;
		cursor: pointer;
	}

	:global(.save:disabled),
	:global(.danger:disabled) {
		opacity: 0.5;
		cursor: default;
	}

	:global(.danger-link) {
		align-self: flex-start;
		background: none;
		border: none;
		color: var(--color-error);
		text-decoration: underline;
		cursor: pointer;
		padding: 0;
		font-size: 0.85rem;
	}

	:global(.confirm-actions) {
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	:global(.confirm-actions .cancel) {
		background: none;
		border: none;
		color: var(--color-text-muted);
		cursor: pointer;
		padding: 0;
		font-size: 0.85rem;
	}

	:global(.danger) {
		background: var(--color-error);
		color: var(--color-surface);
		border: none;
		border-radius: 0.5rem;
		padding: 0.4rem 0.75rem;
		cursor: pointer;
		font-size: 0.85rem;
	}

	:global(.hint) {
		color: var(--color-text-muted);
		margin: 0.25rem 0 0;
	}

	:global(.hint.error) {
		color: var(--color-error);
	}

	:global(.hint.ok) {
		color: var(--color-success, #4caf50);
	}

	:global(.section-header-row) {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		flex-wrap: wrap;
	}

	:global(.save.small) {
		padding: 0.35rem 0.75rem;
		font-size: 0.85rem;
	}
</style>
