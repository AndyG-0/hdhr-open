<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import favicon from '$lib/assets/favicon.svg';
	import '../app.css';
	import { _ } from 'svelte-i18n';
	import { waitLocale, loadLocaleFromServer } from '$lib/i18n';
	// Imported for its side effect: subscribing keeps document.documentElement's
	// data-theme attribute (and localStorage) in sync with the store.
	import { loadThemeFromServer } from '$lib/stores/theme';
	import { user, userLoaded, loadCurrentUser } from '$lib/stores/user';
	import { needsSetup, setupStatusLoaded, setupStatusError, loadSetupStatus } from '$lib/stores/setup';
	import { api } from '$lib/api';
	import { aiDrawerOpen, toggleAIDrawer } from '$lib/stores/ai-drawer';
	import { loadOnceWhen } from '$lib/load-once.svelte';
	import AIAssistantDrawer from '$lib/components/ai/AIAssistantDrawer.svelte';
	import HDHomeRunPlayer from '$lib/components/HDHomeRunPlayer.svelte';
	import { playback, keepPlayingOnNavigate, stopPlayback } from '$lib/stores/playback';

	let { children } = $props();

	// Gates rendering until the initial locale's catalog has loaded, so no
	// raw translation key (e.g. "layout.fatal_title") ever flashes on first load.
	let i18nReady = $state(false);

	// Any household member (not just admins) can read /api/network-settings/ai
	// (see backend/app/api/network_settings.py — only PATCH/test-connection
	// require admin), so this checks whether the assistant is actually usable
	// before showing its nav entry to a non-admin who couldn't configure it anyway.
	let aiConfigured = $state(false);

	loadOnceWhen(
		() => Boolean($user),
		() => {
			api
				.getNetworkIntegration('ai')
				.then((row) => {
					aiConfigured = Boolean(row.settings.has_api_key && row.settings.model);
				})
				.catch(() => {
					aiConfigured = false;
				});
		},
	);

	onMount(async () => {
		await waitLocale();
		i18nReady = true;

		// Resolved before loadCurrentUser() so the redirect effect below can
		// decide setup-vs-login before either store's data actually matters.
		await loadSetupStatus();
		await loadCurrentUser();
	});

	// Three-way redirect: unreachable backend gets its own message (below),
	// a fresh install goes to /setup, everyone else falls through to the
	// existing "no session -> /login" check. Order matters — $needsSetup and
	// $userLoaded are only meaningful once their respective loads resolve.
	$effect(() => {
		if (!$setupStatusLoaded || $setupStatusError) return;

		if ($needsSetup) {
			if (page.url.pathname !== '/setup') goto('/setup');
			return;
		}
		if (page.url.pathname === '/setup') {
			goto('/login');
			return;
		}

		if (!$userLoaded) return;
		if (!$user && page.url.pathname !== '/login') {
			goto('/login');
		}
	});

	$effect(() => {
		if ($user) {
			loadThemeFromServer();
			loadLocaleFromServer();
		}
	});

	// The player instance keeps playing across route changes so an AirPlay
	// route or Cast session survives navigation (see HDHomeRunPlayer's
	// attachPlayer destroy(), which only tears down when this component
	// actually unmounts) - full vs. mini is just which page started it.
	const displayMode = $derived.by<'full' | 'mini'>(() =>
		$playback.media && $playback.originPath === page.url.pathname ? 'full' : 'mini',
	);

	$effect(() => {
		// Re-run whenever the route changes; stop playback on navigate-away
		// unless the user has opted to keep it going.
		void page.url.pathname;
		if (
			$playback.media &&
			$playback.originPath !== page.url.pathname &&
			!$keepPlayingOnNavigate
		) {
			stopPlayback();
		}
	});
</script>

<svelte:head>
	<title>HDHR Open</title>
	<link rel="icon" href={favicon} />
</svelte:head>

{#if i18nReady}
	{#if $setupStatusError}
		<div class="fatal-error">
			<h2>{$_('layout.fatal_title')}</h2>
			<p class="hint">{$_('layout.fatal_hint')}</p>
		</div>
	{:else}
		{#if $user && page.url.pathname !== '/login' && page.url.pathname !== '/setup' && page.url.pathname !== '/player'}
			<nav class="app-nav">
				<a href="/" class:active={page.url.pathname === '/'}>{$_('layout.nav_guide')}</a>
				<a href="/recordings" class:active={page.url.pathname === '/recordings'}>{$_('layout.nav_recordings')}</a>
				<a href="/settings" class:active={page.url.pathname === '/settings'}>{$_('layout.nav_settings')}</a>
				{#if aiConfigured}
					<button class="app-nav-button" class:active={$aiDrawerOpen} onclick={toggleAIDrawer}>
						{$_('layout.nav_ask_ai')}
					</button>
				{/if}
			</nav>
		{/if}

		{@render children()}

		{#if $playback.media && page.url.pathname !== '/player'}
			<HDHomeRunPlayer
				src={$playback.media.url}
				title={$playback.media.title}
				playUrl={$playback.media.playUrl}
				recordingId={$playback.media.recordingId}
				watchSessionId={$playback.media.watchSessionId}
				startTimestamp={$playback.media.startTimestamp}
				recordEndTimestamp={$playback.media.recordEndTimestamp}
				seekable={$playback.media.seekable}
				isWatchSession={$playback.media.isWatchSession}
				channel={$playback.media.channel}
				airing={$playback.media.airing}
				channels={$playback.context?.channels ?? []}
				favoriteChannels={$playback.context?.favoriteChannels ?? new Set()}
				recordingRules={$playback.context?.recordingRules ?? []}
				pendingRuleIds={$playback.context?.pendingRuleIds ?? new Set()}
				officialDvrActive={$playback.context?.officialDvrActive ?? false}
				recordingLoading={$playback.context?.recordingLoading ?? null}
				onRecordEpisode={$playback.context?.onRecordEpisode}
				onRecordSeries={$playback.context?.onRecordSeries}
				onUpdateRule={$playback.context?.onUpdateRule}
				onCancelRule={$playback.context?.onCancelRule}
				onToggleFavorite={$playback.context?.onToggleFavorite}
				onChannelChange={$playback.context?.onChannelChange}
				allowPopout={displayMode === 'full'}
				displayMode={displayMode}
				onExpand={() => goto($playback.originPath ?? '/')}
				onClose={stopPlayback}
			/>
		{/if}

		{#if $user && page.url.pathname !== '/player'}
			<AIAssistantDrawer />
		{/if}
	{/if}
{/if}

<style>
	.app-nav {
		display: flex;
		gap: 0.25rem;
		padding: 0.5rem 1rem;
		border-bottom: 1px solid var(--color-border);
	}

	.app-nav a {
		padding: 0.4rem 0.75rem;
		border-radius: 0.5rem;
		font-size: 0.9rem;
		color: var(--color-text-muted);
		text-decoration: none;
	}

	.app-nav a.active {
		background: var(--color-accent);
		color: var(--color-surface);
	}

	.app-nav-button {
		padding: 0.4rem 0.75rem;
		border-radius: 0.5rem;
		font-size: 0.9rem;
		color: var(--color-text-muted);
		background: none;
		border: none;
		font: inherit;
		cursor: pointer;
	}

	.app-nav-button.active {
		background: var(--color-accent);
		color: var(--color-surface);
	}

	.fatal-error {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		padding: 2rem;
		text-align: center;
	}

	.hint {
		color: var(--color-text-muted);
		margin: 0;
		font-size: 0.9rem;
	}
</style>
