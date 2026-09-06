<script lang="ts">
	import type { Component } from 'svelte';
	import HDHomeRunPlayer from '$lib/components/HDHomeRunPlayer.svelte';
	import { playback, stopPlayback } from '$lib/stores/playback';

	// Mirrors the player-rendering block in routes/+layout.svelte (CAST-4):
	// the real player is mounted at the layout root, not by each page, so
	// route-component tests need this stand-in to see it render.
	interface Props {
		page: Component;
	}

	let { page: PageComponent }: Props = $props();
</script>

<PageComponent />

{#if $playback.media}
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
		allowPopout={true}
		displayMode="full"
		onExpand={() => {}}
		onClose={stopPlayback}
	/>
{/if}
