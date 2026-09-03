<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import { api } from '$lib/api';
	import {
		watchCastState,
		requestCastSession,
		loadCastMedia,
		endCastSession,
		getActiveCastSessionId,
		setActiveCastSessionId,
		type CastState,
	} from '$lib/cast/cast-loader';

	interface Props {
		title: string;
		subtitle?: string;
		posterUrl?: string;
		// Called only when the user actually clicks to start casting (not
		// eagerly) - mints a for_cast=true HLS session on the backend and
		// returns its absolute playlist URL plus session id, so this
		// component can tear that session down itself once casting ends.
		buildContentUrl: () => Promise<{ url: string; sessionId: string }>;
		// Lets the parent player pause/hide local playback while the stream
		// is on the receiver instead of double-playing it locally too.
		onCastingChange?: (casting: boolean) => void;
	}

	let { title, subtitle, posterUrl, buildContentUrl, onCastingChange }: Props = $props();

	let available = $state(false);
	let casting = $state(false);
	let connecting = $state(false);
	let errorMessage = $state<string | null>(null);

	let wasCasting = false;
	let unsubscribe: (() => void) | null = null;

	function stopBackendSession() {
		const sessionId = getActiveCastSessionId();
		if (sessionId) {
			api.stopHlsSession(sessionId);
			setActiveCastSessionId(null);
		}
	}

	onMount(() => {
		unsubscribe = watchCastState((state: CastState) => {
			available = state !== 'no_devices_available';
			const nowCasting = state === 'connected';
			// A session end the user (or receiver) triggered outside this
			// button - e.g. stopping from the Google Home app - still has to
			// tear down the backend's cast-token HLS session, or it just sits
			// idle until the reaper eventually catches it.
			if (wasCasting && !nowCasting) {
				stopBackendSession();
				onCastingChange?.(false);
			}
			casting = nowCasting;
			wasCasting = nowCasting;
		});
	});

	// Deliberately does NOT call endCastSession()/stopBackendSession() here.
	// window.cast's CastContext is page/tab-scoped and survives a SvelteKit
	// client-side navigation on its own; this component unmounting just means
	// the *current page* went away, not that the user wants casting to stop.
	// The backend session is still torn down correctly later - by whichever
	// CastButton is mounted next, via the module-level session id above, on
	// an explicit stop-click or a receiver-side disconnect.
	onDestroy(() => {
		unsubscribe?.();
	});

	async function handleClick() {
		if (casting) {
			endCastSession();
			return;
		}
		connecting = true;
		errorMessage = null;
		try {
			// requestCastSession() opens Chrome's native device picker, which
			// only works while this click's user-activation is still live - it
			// must run (and be awaited) before any other async work, or the
			// picker never appears and this hangs forever. Only mint the
			// backend's for_cast HLS session (slow - ffmpeg has to spin up)
			// once a receiver is actually connected.
			const session = await requestCastSession();
			try {
				const { url, sessionId: sid } = await buildContentUrl();
				setActiveCastSessionId(sid);
				await loadCastMedia(session, {
					contentUrl: url,
					contentType: 'application/x-mpegurl',
					title,
					subtitle,
					imageUrl: posterUrl,
				});
				onCastingChange?.(true);
			} catch (err) {
				// A receiver is already connected at this point (requestCastSession
				// above succeeded) - leaving it connected with nothing loaded would
				// strand the user on a "connected but blank" receiver, so tear the
				// session down too, not just the backend's HLS session.
				endCastSession();
				throw err;
			}
		} catch (err) {
			errorMessage = err instanceof Error && err.message ? err.message : 'Failed to start casting';
			stopBackendSession();
		} finally {
			connecting = false;
		}
	}
</script>

{#if available}
	<button
		class="control-btn"
		class:active={casting}
		disabled={connecting}
		onclick={handleClick}
		aria-label={casting ? $_('player.cast_stop') : $_('player.cast')}
		title={errorMessage ?? (casting ? $_('player.cast_stop') : $_('player.cast'))}
	>
		📺 {#if connecting}{$_('player.cast_connecting')}{:else if casting}{$_('player.cast_connected')}{:else}{$_(
				'player.cast',
			)}{/if}
	</button>
{/if}

<style>
	.control-btn {
		background: rgba(255, 255, 255, 0.15);
		border: 1px solid rgba(255, 255, 255, 0.3);
		border-radius: 0.4rem;
		padding: 0.3rem 0.6rem;
		color: #fff;
		font-size: 0.85rem;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.control-btn:hover {
		background: rgba(255, 255, 255, 0.25);
	}

	.control-btn.active {
		background: rgba(56, 189, 248, 0.25);
		border-color: #38bdf8;
		color: #38bdf8;
	}

	.control-btn:disabled {
		opacity: 0.6;
		cursor: default;
	}
</style>
