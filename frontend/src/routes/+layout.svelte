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

	let { children } = $props();

	// Gates rendering until the initial locale's catalog has loaded, so no
	// raw translation key (e.g. "layout.fatal_title") ever flashes on first load.
	let i18nReady = $state(false);

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
		{#if $user && page.url.pathname !== '/login' && page.url.pathname !== '/setup'}
			<nav class="app-nav">
				<a href="/" class:active={page.url.pathname === '/'}>{$_('layout.nav_guide')}</a>
				<a href="/recordings" class:active={page.url.pathname === '/recordings'}>{$_('layout.nav_recordings')}</a>
				<a href="/settings" class:active={page.url.pathname === '/settings'}>{$_('layout.nav_settings')}</a>
			</nav>
		{/if}

		{@render children()}
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
