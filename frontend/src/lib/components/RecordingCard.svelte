<script lang="ts">
	import type { HDHomeRunRecording } from '$lib/api';
	import { _ } from 'svelte-i18n';
	import { get } from 'svelte/store';

	interface Props {
		recording: HDHomeRunRecording;
		variant: 'in-progress' | 'completed';
		failed: boolean;
		onImageError: () => void;
		onWatchLive?: () => void;
		onPlay?: () => void;
	}

	let { recording, variant, failed, onImageError, onWatchLive, onPlay }: Props = $props();

	function formatBytes(bytes: number | null | undefined): string {
		if (bytes === null || bytes === undefined) return get(_)('common.unknown');
		const gb = bytes / 1_000_000_000;
		return `${gb.toFixed(1)} GB`;
	}

	function formatTime(seconds: number | null | undefined): string {
		if (seconds === null || seconds === undefined) return '';
		return new Date(seconds * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	}

	function formatDate(seconds: number | null | undefined): string {
		if (seconds === null || seconds === undefined) return '';
		return new Date(seconds * 1000).toLocaleString([], {
			month: 'short',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		});
	}

	function formatDuration(seconds: number | null | undefined): string {
		if (seconds == null || seconds <= 0) return '';
		const mins = Math.round(seconds / 60);
		if (mins < 60) return `${mins}m`;
		const hours = Math.floor(mins / 60);
		const remMins = mins % 60;
		return remMins > 0 ? `${hours}h ${remMins}m` : `${hours}h`;
	}

	function formatResolution(width?: number | null, height?: number | null): string | null {
		if (!height) return null;
		if (height >= 2160) return '4K';
		if (height >= 1080) return '1080p';
		if (height >= 720) return '720p';
		if (height >= 480) return '480p';
		return `${height}p`;
	}

	function formatAudio(channels?: number | null, codec?: string | null): string | null {
		if (channels && channels >= 6) return '5.1';
		if (channels && channels === 2) return 'Stereo';
		if (codec) {
			const c = codec.toLowerCase();
			if (c.includes('ac3') || c.includes('eac3') || c.includes('dolby')) return 'Dolby';
			if (c.includes('aac')) return 'AAC';
		}
		return null;
	}

	function handleKeydown(e: KeyboardEvent) {
		if ((e.key === 'Enter' || e.key === ' ') && onPlay) {
			onPlay();
		}
	}

	function getCategoryType(rec: HDHomeRunRecording): 'shows' | 'movies' | 'sports' {
		if (rec.category_type) return rec.category_type;
		const t = (rec.title || '').toLowerCase();
		const ep = (rec.episode_title || '').toLowerCase();
		const cat = (rec.category || '').toLowerCase();
		const sports = [
			'sport',
			'sports',
			'football',
			'basketball',
			'baseball',
			'hockey',
			'soccer',
			'golf',
			'tennis',
			'racing',
			'nascar',
			'formula 1',
			'f1',
			'olympics',
			'wrestling',
			'boxing',
			'mma',
			'ufc',
			'wwe',
			'nfl',
			'nba',
			'mlb',
			'nhl',
			'pga',
			'mls',
			'premier league',
			'champions league',
			'uefa',
			'fifa',
			'ncaa',
			'college football',
			'college basketball',
		];
		if (
			sports.some((k) => cat.includes(k) || t.includes(k)) ||
			ep.includes(' at ') ||
			ep.includes(' vs ') ||
			ep.includes(' vs. ') ||
			ep.includes(' @ ')
		) {
			return 'sports';
		}
		const movies = ['movie', 'feature film', 'film', 'cinema'];
		if (movies.some((k) => cat.includes(k) || t.includes(k))) {
			return 'movies';
		}
		return 'shows';
	}

	function getPlaceholderIcon(rec: HDHomeRunRecording): string {
		const catType = getCategoryType(rec);
		if (catType === 'movies') return '🎬';
		if (catType === 'sports') {
			const t = `${rec.title || ''} ${rec.episode_title || ''} ${rec.category || ''}`.toLowerCase();
			if (t.includes('football') || t.includes('nfl') || t.includes('ncaa football')) return '🏈';
			if (t.includes('basketball') || t.includes('nba')) return '🏀';
			if (t.includes('baseball') || t.includes('mlb')) return '⚾';
			if (
				t.includes('soccer') ||
				t.includes('mls') ||
				t.includes('premier league') ||
				t.includes('fifa') ||
				t.includes('champions league')
			)
				return '⚽';
			if (t.includes('hockey') || t.includes('nhl')) return '🏒';
			if (t.includes('golf') || t.includes('pga')) return '⛳';
			if (t.includes('racing') || t.includes('nascar') || t.includes('formula 1') || t.includes('f1')) return '🏎️';
			if (t.includes('boxing') || t.includes('mma') || t.includes('ufc') || t.includes('wwe') || t.includes('wrestling'))
				return '🥊';
			return '🏆';
		}
		return '📺';
	}
</script>

{#snippet poster()}
	{#if recording.image_url && !failed}
		<img class="rec-thumb" src={recording.image_url} alt="" onerror={onImageError} />
	{:else}
		<div class="rec-thumb rec-thumb-placeholder" aria-hidden="true">{getPlaceholderIcon(recording)}</div>
	{/if}
{/snippet}

{#if variant === 'in-progress'}
	<div class="recording in-progress-card">
		{@render poster()}
		<div class="rec-info">
			<div class="rec-status-line">
				<span class="rec-server-badge {recording.provider ?? 'builtin'}">
					{recording.provider === 'hdhomerun'
						? $_('hdhomerun.detail.server_badge_hdhomerun')
						: $_('hdhomerun.detail.server_badge_builtin')}
				</span>
				<span class="rec-badge">{$_('hdhomerun.tile.recording_badge')}</span>
				{#if recording.record_end}
					<span class="rec-end"
						>{$_('hdhomerun.detail.recording_until', { values: { time: formatTime(recording.record_end) } })}</span
					>
				{/if}
			</div>
			<span class="rec-title">{recording.title}</span>
			{#if recording.episode_title}<span class="rec-sub">{recording.episode_title}</span>{/if}
			{#if recording.synopsis}<p class="rec-synopsis">{recording.synopsis}</p>{/if}
			<div class="rec-meta">
				{#if recording.channel_name || recording.channel_number}
					<span class="rec-channel"
						>{recording.channel_number ? `${recording.channel_number} ` : ''}{recording.channel_name || ''}</span
					>
				{/if}
				{#if recording.category}
					<span class="rec-category-tag">{recording.category}</span>
				{/if}
				<span class="rec-progress-notice">{$_('hdhomerun.detail.recording_in_progress_hint')}</span>
			</div>
		</div>
		<div class="rec-actions">
			{#if recording.channel_number}
				<button type="button" class="watch-live-btn small" onclick={onWatchLive}>
					{$_('hdhomerun.detail.watch_live_button')}
				</button>
			{/if}
		</div>
	</div>
{:else}
	<div class="recording clickable" role="button" tabindex="0" onclick={onPlay} onkeydown={handleKeydown}>
		{@render poster()}
		<div class="rec-info">
			<span class="rec-title">{recording.title}</span>
			{#if recording.episode_title}<span class="rec-sub">{recording.episode_title}</span>{/if}
			{#if recording.synopsis}<p class="rec-synopsis">{recording.synopsis}</p>{/if}
			<div class="rec-meta">
				<span class="rec-server-badge {recording.provider ?? 'builtin'}">
					{recording.provider === 'hdhomerun'
						? $_('hdhomerun.detail.server_badge_hdhomerun')
						: $_('hdhomerun.detail.server_badge_builtin')}
				</span>
				{#if recording.channel_name}<span class="rec-channel">{recording.channel_name}</span>{/if}
				{#if recording.start}<span class="rec-end">{formatDate(recording.start)}</span>{/if}
				{#if recording.duration_seconds}
					<span class="rec-meta-item">{formatDuration(recording.duration_seconds)}</span>
				{/if}
				{#if recording.file_size_bytes}
					<span class="rec-meta-item">{formatBytes(recording.file_size_bytes)}</span>
				{/if}
				{#if formatResolution(recording.video_width, recording.video_height)}
					<span class="rec-media-tag resolution">{formatResolution(recording.video_width, recording.video_height)}</span>
				{/if}
				{#if recording.has_captions}
					<span class="rec-media-tag cc">CC</span>
				{/if}
				{#if formatAudio(recording.audio_channels, recording.audio_codec)}
					<span class="rec-media-tag audio">{formatAudio(recording.audio_channels, recording.audio_codec)}</span>
				{/if}
				{#if recording.category}
					<span class="rec-category-tag">{recording.category}</span>
				{/if}
			</div>
		</div>
		<div class="rec-actions">
			<button
				class="watch small"
				onclick={(e) => {
					e.stopPropagation();
					onPlay?.();
				}}
			>
				▶ {$_('hdhomerun.detail.watch_button')}
			</button>
			{#if recording.play_url}
				<a
					class="open-external small"
					href={recording.play_url}
					target="_blank"
					rel="noopener noreferrer"
					onclick={(e) => e.stopPropagation()}
				>
					{$_('hdhomerun.detail.open_external')}
				</a>
			{/if}
		</div>
	</div>
{/if}

<style>
	.recording {
		display: flex;
		flex-direction: column;
		font-size: 0.9rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.6rem 0.6rem 0.75rem;
		overflow: hidden;
	}

	.recording.in-progress-card {
		border: 1px solid var(--color-error);
		box-shadow: 0 0 0 1px var(--color-error);
	}

	.recording.clickable {
		cursor: pointer;
		transition:
			background 0.15s ease,
			border-color 0.15s ease,
			transform 0.15s ease;
	}

	.recording.clickable:hover {
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.08));
		border-color: var(--color-accent, #3b82f6);
		transform: translateY(-2px);
	}

	.rec-thumb {
		width: 100%;
		aspect-ratio: 2 / 3;
		object-fit: cover;
		border-radius: 0.35rem;
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.05));
		margin-bottom: 0.6rem;
	}

	.rec-thumb-placeholder {
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 2.75rem;
		border: 1px solid var(--color-border);
	}

	.rec-info {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		flex: 1;
	}

	.rec-status-line {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		flex-wrap: wrap;
	}

	.rec-progress-notice {
		color: var(--color-text-muted);
		font-style: italic;
		font-size: 0.75rem;
	}

	.rec-sub {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.rec-synopsis {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		margin: 0.1rem 0 0;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.rec-meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.75rem;
	}

	.rec-meta-item {
		color: var(--color-text-muted);
		font-size: 0.72rem;
	}

	.rec-media-tag {
		font-size: 0.65rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 0.08rem 0.3rem;
		border-radius: 0.25rem;
		border: 1px solid var(--color-border);
		color: var(--color-text-muted);
		background: var(--color-surface);
	}

	.rec-media-tag.resolution {
		border-color: var(--color-accent);
		color: var(--color-accent);
	}

	.rec-media-tag.cc {
		font-weight: 700;
		color: var(--color-text);
	}

	.rec-category-tag {
		font-size: 0.68rem;
		color: var(--color-text-muted);
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.08));
		border-radius: 0.25rem;
		padding: 0.08rem 0.3rem;
	}

	.rec-badge {
		color: var(--color-error);
		font-weight: 600;
		font-size: 0.75rem;
	}

	.rec-title {
		font-weight: 600;
	}

	.rec-channel,
	.rec-end {
		color: var(--color-text-muted);
	}

	.rec-actions {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-top: 0.5rem;
	}

	.rec-server-badge {
		font-size: 0.68rem;
		padding: 0.1rem 0.35rem;
		border-radius: 0.3rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		color: var(--color-text-muted);
	}

	.rec-server-badge.hdhomerun {
		border-color: var(--color-accent);
		color: var(--color-accent);
	}

	.watch {
		background: var(--color-accent);
		color: var(--color-surface);
		border: none;
		border-radius: 0.5rem;
		padding: 0.35rem 0.75rem;
		font-size: 0.85rem;
		cursor: pointer;
	}

	.watch.small {
		padding: 0.2rem 0.5rem;
		font-size: 0.75rem;
	}

	.open-external {
		color: var(--color-accent);
		font-size: 0.85rem;
	}

	.open-external.small {
		font-size: 0.75rem;
		padding: 0.25rem 0.5rem;
	}

	.watch-live-btn {
		background: var(--color-accent);
		color: var(--color-surface);
		border: none;
		border-radius: 0.5rem;
		padding: 0.35rem 0.75rem;
		font-size: 0.85rem;
		cursor: pointer;
		font-weight: 500;
		transition: opacity 0.15s ease;
	}

	.watch-live-btn:hover {
		opacity: 0.9;
	}

	.watch-live-btn.small {
		padding: 0.2rem 0.55rem;
		font-size: 0.75rem;
	}
</style>
