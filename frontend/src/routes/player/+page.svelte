<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';
	import {
		api,
		type HDHomeRunChannel,
		type HDHomeRunGuideEntry,
		type HDHomeRunRecording,
		type HDHomeRunRecordingRule,
		type RecordingRuleOptions,
	} from '$lib/api';
	import HDHomeRunPlayer from '$lib/components/HDHomeRunPlayer.svelte';

	const WATCH_HEARTBEAT_INTERVAL_MS = 20_000;

	let loading = $state(true);
	let error = $state<string | null>(null);

	let channels = $state<HDHomeRunChannel[]>([]);
	let favoriteChannels = $state<Set<string>>(new Set());
	let recordingRules = $state<HDHomeRunRecordingRule[]>([]);
	let officialDvrActive = $state(false);
	let playbackMode = $state('server_transcode');

	let watchSessionId = $state<string | null>(null);
	let watchHeartbeatHandle: ReturnType<typeof setInterval> | undefined;

	let playingMedia = $state<{
		title: string;
		url: string;
		playUrl?: string;
		recordingId?: string | null;
		watchSessionId?: string | null;
		startTimestamp?: number | null;
		recordEndTimestamp?: number | null;
		seekable?: boolean;
		isWatchSession?: boolean;
		channel?: HDHomeRunChannel | null;
		airing?: HDHomeRunGuideEntry | null;
	} | null>(null);

	function stopWatchSession() {
		if (watchHeartbeatHandle !== undefined) {
			clearInterval(watchHeartbeatHandle);
			watchHeartbeatHandle = undefined;
		}
		if (watchSessionId) {
			api.stopWatch(watchSessionId);
			watchSessionId = null;
		}
	}

	function handleClose() {
		stopWatchSession();
		if (typeof window !== 'undefined') {
			if (window.opener) {
				window.close();
				return;
			}
			goto('/');
		}
	}

	onMount(() => {
		window.addEventListener('pagehide', stopWatchSession);
		loadAll();

		return () => {
			window.removeEventListener('pagehide', stopWatchSession);
			stopWatchSession();
		};
	});

	onDestroy(() => {
		stopWatchSession();
	});

	async function loadAll() {
		loading = true;
		error = null;

		try {
			// Load peripheral data (favorites, playback mode, rules, channels)
			try {
				const integration = await api.getNetworkIntegration('hdhomerun');
				if (Array.isArray(integration.settings.favorite_channels)) {
					favoriteChannels = new Set(integration.settings.favorite_channels as string[]);
				}
				if (integration.settings.playback_mode) {
					playbackMode = String(integration.settings.playback_mode);
				}
			} catch {
				// Non-fatal
			}

			try {
				const dvr = await api.getDvrInfo();
				officialDvrActive = dvr.is_builtin === false;
			} catch {
				officialDvrActive = false;
			}

			try {
				recordingRules = await api.listRecordingRules();
			} catch {
				recordingRules = [];
			}

			const channelParam = page.url.searchParams.get('channel');
			const recordingParam = page.url.searchParams.get('recording');
			const playUrlParam = page.url.searchParams.get('play_url');
			const titleParam = page.url.searchParams.get('title');

			if (channelParam) {
				await loadChannel(channelParam);
			} else if (recordingParam) {
				await loadRecording(recordingParam, titleParam);
			} else if (playUrlParam) {
				loadDirectPlay(playUrlParam, titleParam);
			} else {
				error = 'No channel, recording, or play_url specified.';
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'Failed to initialize player';
		} finally {
			loading = false;
		}
	}

	async function loadChannel(channelNumber: string) {
		let channelList: HDHomeRunChannel[] = [];
		try {
			const res = await api.getHDHomeRunChannels();
			channels = res.channels;
			channelList = res.channels;
		} catch {
			channelList = [];
		}

		const channel = channelList.find((c) => c.channel_number === channelNumber) ?? {
			channel_number: channelNumber,
			name: channelNumber,
			is_hd: true,
			is_drm: false,
			stream_url: '',
			playback_url: `/auto/v${channelNumber}`,
			now: null,
			next: null,
		};

		// Try loading guide entry for current airing metadata
		let currentAiring: HDHomeRunGuideEntry | null = null;
		try {
			const fullGuide = await api.getHDHomeRunGuide();
			const nowSec = Math.floor(Date.now() / 1000);
			const guideEntry = fullGuide?.find((g) => g.channel_number === channel.channel_number);
			currentAiring =
				guideEntry?.airings.find((a) => a.start !== null && a.end !== null && a.start <= nowSec && a.end > nowSec) ??
				channel.now ??
				null;
		} catch {
			currentAiring = channel.now ?? null;
		}

		const title = `${channel.channel_number} ${channel.name}`;
		const nowSec = Math.floor(Date.now() / 1000);

		// Auto-start capture for rewind/pause on live watch
		let watchRecording: {
			recording_id?: string | null;
			session_id?: string | null;
			play_url?: string | null;
			start?: number | null;
		} | null = null;

		try {
			watchRecording = await api.startWatch(channel.channel_number);
		} catch {
			// Fall back to plain live stream
		}

		if (watchRecording?.recording_id && watchRecording.session_id) {
			watchSessionId = watchRecording.session_id;
			playingMedia = {
				title,
				url: api.hdhomerunPlaybackUrl(channel.playback_url ?? `/auto/v${channel.channel_number}`),
				playUrl: watchRecording.play_url ?? channel.playback_url ?? `/auto/v${channel.channel_number}`,
				recordingId: watchRecording.recording_id,
				watchSessionId: watchRecording.session_id,
				startTimestamp: watchRecording.start ?? nowSec,
				recordEndTimestamp: null,
				seekable: true,
				isWatchSession: true,
				channel,
				airing: currentAiring,
			};

			watchHeartbeatHandle = setInterval(() => {
				if (watchSessionId) {
					api.heartbeatWatch(watchSessionId).catch(() => {});
				}
			}, WATCH_HEARTBEAT_INTERVAL_MS);
			return;
		}

		// Fallback plain live
		playingMedia = {
			title,
			url: api.hdhomerunPlaybackUrl(channel.playback_url ?? `/auto/v${channel.channel_number}`),
			playUrl: channel.playback_url ?? `/auto/v${channel.channel_number}`,
			recordingId: null,
			startTimestamp: null,
			recordEndTimestamp: null,
			seekable: false,
			channel,
			airing: currentAiring,
		};
	}

	async function loadRecording(recordingId: string, fallbackTitle?: string | null) {
		const recs = await api.listRecordings();
		const recording = recs.find((r) => r.recording_id === recordingId);
		if (!recording) {
			error = 'Recording not found.';
			return;
		}

		let playUrl = recording.play_url;
		if (!playUrl && recording.recording_id) {
			playUrl = `/recorded/${recording.recording_id}`;
		}
		if (!playUrl && recording.channel_number) {
			playUrl = `/auto/v${recording.channel_number}`;
		}
		if (!playUrl) {
			error = 'Recording has no playable stream.';
			return;
		}

		const seekable = recording.is_dvr_file === true && playbackMode === 'server_transcode';
		const streamUrl = api.hdhomerunRecordingStreamUrl(playUrl);
		const computedTitle = recording.episode_title
			? `${recording.title} - ${recording.episode_title}`
			: recording.title;

		playingMedia = {
			title: fallbackTitle || computedTitle,
			url: streamUrl,
			playUrl,
			recordingId: recording.recording_id ?? null,
			startTimestamp: recording.start,
			recordEndTimestamp: recording.record_end,
			seekable,
		};
	}

	function loadDirectPlay(playUrl: string, title?: string | null) {
		const isRecorded = playUrl.startsWith('/recorded/') || playUrl.includes('recording');
		const streamUrl = isRecorded ? api.hdhomerunRecordingStreamUrl(playUrl) : api.hdhomerunPlaybackUrl(playUrl);

		playingMedia = {
			title: title || 'HDHomeRun Player',
			url: streamUrl,
			playUrl,
			recordingId: null,
			startTimestamp: null,
			recordEndTimestamp: null,
			seekable: isRecorded,
		};
	}

	async function recordEpisode(
		seriesId?: string | null,
		channelNumber?: string,
		start?: number | null,
		options?: RecordingRuleOptions,
	) {
		await api.addHDHomeRunRecordingRule({
			series_id: seriesId ?? undefined,
			channel: channelNumber ?? options?.channel,
			start_time: start ?? undefined,
			title: options?.title,
			start_padding: options?.startPadding,
			end_padding: options?.endPadding,
		});
		recordingRules = await api.listRecordingRules();
	}

	async function recordSeries(
		seriesId: string,
		channelNumber?: string,
		options?: RecordingRuleOptions,
	) {
		await api.addHDHomeRunRecordingRule({
			series_id: seriesId,
			channel: channelNumber ?? options?.channel,
			title: options?.title,
			recent_only: options?.recentOnly,
			start_padding: options?.startPadding,
			end_padding: options?.endPadding,
		});
		recordingRules = await api.listRecordingRules();
	}

	async function updateRule(
		ruleId: string,
		mode: 'episode' | 'series',
		options: RecordingRuleOptions,
	) {
		await api.updateHDHomeRunRecordingRule(ruleId, {
			channel: options.channel,
			title: options.title,
			start_padding: options.startPadding,
			end_padding: options.endPadding,
			recent_only: options.recentOnly,
		});
		recordingRules = await api.listRecordingRules();
	}

	async function cancelRule(ruleId: string) {
		await api.deleteHDHomeRunRecordingRule(ruleId);
		recordingRules = await api.listRecordingRules();
	}

	async function toggleFavorite(channelNumber: string) {
		const next = new Set(favoriteChannels);
		if (next.has(channelNumber)) {
			next.delete(channelNumber);
		} else {
			next.add(channelNumber);
		}
		favoriteChannels = next;
		await api.updateNetworkIntegration('hdhomerun', { favorite_channels: [...next] });
	}
</script>

<svelte:head>
	<title>{playingMedia?.title ?? 'HDHR Popout Player'}</title>
</svelte:head>

<div class="popout-player-container">
	{#if loading}
		<div class="status-screen">
			<p class="status-hint">{$_('common.loading')}</p>
		</div>
	{:else if error}
		<div class="status-screen">
			<p class="status-error">⚠️ {error}</p>
			<button type="button" class="status-btn" onclick={handleClose}>
				{$_('player.close', { default: 'Close' })}
			</button>
		</div>
	{:else if playingMedia}
		<HDHomeRunPlayer
			src={playingMedia.url}
			title={playingMedia.title}
			playUrl={playingMedia.seekable ? playingMedia.playUrl : undefined}
			recordingId={playingMedia.seekable ? playingMedia.recordingId : undefined}
			watchSessionId={playingMedia.watchSessionId}
			startTimestamp={playingMedia.seekable ? playingMedia.startTimestamp : undefined}
			recordEndTimestamp={playingMedia.seekable ? playingMedia.recordEndTimestamp : undefined}
			seekable={playingMedia.seekable}
			isWatchSession={playingMedia.isWatchSession}
			channel={playingMedia.channel}
			airing={playingMedia.airing}
			{channels}
			{favoriteChannels}
			{recordingRules}
			{officialDvrActive}
			allowPopout={false}
			onRecordEpisode={recordEpisode}
			onRecordSeries={recordSeries}
			onUpdateRule={updateRule}
			onCancelRule={cancelRule}
			onToggleFavorite={toggleFavorite}
			onClose={handleClose}
		/>
	{/if}
</div>

<style>
	:global(html),
	:global(body) {
		margin: 0;
		padding: 0;
		width: 100%;
		height: 100%;
		overflow: hidden;
		background: #000;
	}

	.popout-player-container {
		position: fixed;
		inset: 0;
		width: 100vw;
		height: 100vh;
		background: #000;
		overflow: hidden;
		user-select: none;
	}

	.status-screen {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 100vh;
		width: 100vw;
		background: #000;
		color: #fff;
		gap: 1rem;
		text-align: center;
		padding: 2rem;
		box-sizing: border-box;
	}

	.status-hint {
		color: rgba(255, 255, 255, 0.7);
		font-size: 1rem;
		margin: 0;
	}

	.status-error {
		color: #ef4444;
		font-size: 1rem;
		margin: 0;
	}

	.status-btn {
		margin-top: 0.5rem;
		padding: 0.5rem 1.25rem;
		background: rgba(255, 255, 255, 0.15);
		border: 1px solid rgba(255, 255, 255, 0.25);
		color: #fff;
		border-radius: 0.5rem;
		cursor: pointer;
		font-size: 0.9rem;
		transition: background 0.15s ease;
	}

	.status-btn:hover {
		background: rgba(255, 255, 255, 0.25);
	}
</style>
