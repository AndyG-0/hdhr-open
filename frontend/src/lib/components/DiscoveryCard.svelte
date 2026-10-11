<script lang="ts">
	import type { HDHomeRunGuideEntry } from '$lib/api';
	import { _ } from 'svelte-i18n';

	interface Props {
		airing: HDHomeRunGuideEntry;
		onSelect: () => void;
	}

	let { airing, onSelect }: Props = $props();

	let imageFailed = $state(false);

	// Mirrors the Android/iOS/tvOS `discovery.*` source labels - shown on
	// every non-"personalized" item so users can see why something was
	// recommended.
	const sourceBadgeKey: Record<string, string> = {
		active_rule: 'discovery.source_active_rule',
		favorite_team: 'discovery.source_favorite_team',
		network_pick: 'discovery.source_network_pick',
		new_and_notable: 'discovery.source_new_and_notable',
	};
	const sourceBadgeLabel = $derived(airing.source ? sourceBadgeKey[airing.source] : undefined);

	function formatTime(seconds: number | null): string {
		if (seconds === null) return '';
		return new Date(seconds * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
	}

	function formatDay(seconds: number | null): string {
		if (seconds === null) return '';
		const date = new Date(seconds * 1000);
		const startOfToday = new Date();
		startOfToday.setHours(0, 0, 0, 0);
		const diffDays = Math.floor((date.getTime() - startOfToday.getTime()) / (86400 * 1000));
		if (diffDays === 0) return $_('hdhomerun.detail.guide_today');
		if (diffDays === 1) return $_('hdhomerun.detail.guide_tomorrow');
		return date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			onSelect();
		}
	}
</script>

<div class="discovery-card" role="button" tabindex="0" onclick={onSelect} onkeydown={handleKeydown}>
	{#if airing.image_url && !imageFailed}
		<img class="discovery-thumb" src={airing.image_url} alt="" onerror={() => (imageFailed = true)} />
	{:else}
		<div class="discovery-thumb discovery-thumb-placeholder" aria-hidden="true">📺</div>
	{/if}
	<div class="discovery-info">
		<span class="discovery-title">{airing.title}</span>
		{#if airing.episode_title}<span class="discovery-sub">{airing.episode_title}</span>{/if}
		{#if sourceBadgeLabel}<span class="discovery-source-badge">{$_(sourceBadgeLabel)}</span>{/if}
		<div class="discovery-meta">
			{#if airing.is_new}<span class="discovery-badge new">{$_('hdhomerun.detail.new_badge')}</span>{/if}
			{#if airing.channel_number}<span class="discovery-channel">{airing.channel_number}</span>{/if}
			{#if airing.start !== null}
				<span class="discovery-time">{formatDay(airing.start)} · {formatTime(airing.start)}</span>
			{/if}
		</div>
		{#if airing.category}
			<div class="discovery-categories">
				{#each airing.category
					.split(',')
					.map((c) => c.trim())
					.filter(Boolean) as cat (cat)}
					<span class="discovery-category-tag">{cat}</span>
				{/each}
			</div>
		{/if}
	</div>
</div>

<style>
	.discovery-card {
		display: flex;
		flex-direction: column;
		font-size: 0.9rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.6rem 0.6rem 0.75rem;
		overflow: hidden;
		cursor: pointer;
		transition:
			background 0.15s ease,
			border-color 0.15s ease,
			transform 0.15s ease;
	}

	.discovery-card:hover {
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.08));
		border-color: var(--color-accent, #3b82f6);
		transform: translateY(-2px);
	}

	.discovery-thumb {
		width: 100%;
		aspect-ratio: 2 / 3;
		object-fit: cover;
		border-radius: 0.35rem;
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.05));
		margin-bottom: 0.6rem;
	}

	.discovery-thumb-placeholder {
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 2.75rem;
		border: 1px solid var(--color-border);
	}

	.discovery-info {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.discovery-title {
		font-weight: 600;
		overflow-wrap: break-word;
	}

	.discovery-sub {
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}

	.discovery-meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
		margin-top: 0.15rem;
	}

	.discovery-badge.new {
		color: var(--color-success);
		font-weight: 700;
		font-size: 0.68rem;
		text-transform: uppercase;
	}

	.discovery-source-badge {
		align-self: flex-start;
		font-size: 0.68rem;
		font-weight: 600;
		color: var(--color-text-muted);
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.08));
		border-radius: 0.25rem;
		padding: 0.08rem 0.35rem;
	}

	.discovery-categories {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
		margin-top: 0.3rem;
	}

	.discovery-category-tag {
		font-size: 0.68rem;
		color: var(--color-text-muted);
		background: var(--color-surface-hover, rgba(255, 255, 255, 0.08));
		border-radius: 0.25rem;
		padding: 0.08rem 0.3rem;
	}
</style>
