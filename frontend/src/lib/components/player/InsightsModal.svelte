<script lang="ts">
	import { _ } from 'svelte-i18n';
	import type { InsightsResponse } from '$lib/api';
	import PlayerIcon from './icons/PlayerIcon.svelte';

	interface Props {
		show?: boolean;
		data: InsightsResponse | null;
		loading?: boolean;
		error?: string | null;
		onClose: () => void;
	}

	let { show = true, data = null, loading = false, error = null, onClose }: Props = $props();
</script>

{#if show}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="insights-modal-overlay"
		data-testid="insights-modal"
		onclick={(e) => e.target === e.currentTarget && onClose()}
	>
		<div
			class="insights-modal-card"
			role="dialog"
			aria-modal="true"
			aria-labelledby="insights-title"
			tabindex="-1"
			onclick={(e) => e.stopPropagation()}
		>
			<div class="modal-header">
				<div class="header-title" id="insights-title">
					<PlayerIcon name="insights" size={22} />
					<span>{$_('insights.title', { default: 'Insights' })}</span>
				</div>
				<button
					type="button"
					class="close-btn"
					onclick={onClose}
					aria-label={$_('player.close', { default: 'Close' })}
				>
					&times;
				</button>
			</div>

			<div class="modal-body">
				{#if loading}
					<div class="loading-state">{$_('insights.loading', { default: 'Loading insights…' })}</div>
				{:else if error}
					<div class="error-banner">{error}</div>
				{:else if data?.category === 'sports'}
					{#if data.sports}
						{@const sports = data.sports}
						<div class="sports-section">
							<div class="status-pill status-{sports.status ?? 'unknown'}">
								{#if sports.status === 'live'}
									{$_('insights.status_live', { default: 'Live' })}
								{:else if sports.status === 'scheduled'}
									{$_('insights.status_scheduled', { default: 'Scheduled' })}
								{:else if sports.status === 'finished'}
									{$_('insights.status_finished', { default: 'Final' })}
								{/if}
							</div>
							<div class="scoreboard">
								<div class="team-row">
									<span class="team-name">{sports.home_team ?? '—'}</span>
									<span class="team-score">{sports.home_score ?? '—'}</span>
								</div>
								<div class="team-row">
									<span class="team-name">{sports.away_team ?? '—'}</span>
									<span class="team-score">{sports.away_score ?? '—'}</span>
								</div>
							</div>
							{#if sports.status === 'live' && sports.home_score === null && sports.away_score === null}
								<p class="live-score-note">{$_('insights.live_score_unavailable', { default: 'Live score not available - showing game details only.' })}</p>
							{/if}
							<div class="meta-row">
								{#if sports.league}
									<span class="meta-item">
										<span class="meta-label">{$_('insights.league', { default: 'League' })}:</span>
										{sports.league}
									</span>
								{/if}
								{#if sports.venue}
									<span class="meta-item">
										<span class="meta-label">{$_('insights.venue', { default: 'Venue' })}:</span>
										{sports.venue}
									</span>
								{/if}
							</div>
						</div>
					{:else}
						<div class="empty-state">{$_('insights.event_not_found', { default: "Couldn't find live details for this game." })}</div>
					{/if}
				{:else if data?.tmdb}
					{@const tmdb = data.tmdb}
					<div class="program-section">
						<div class="program-header">
							{#if tmdb.poster_url}
								<img class="poster" src={tmdb.poster_url} alt={tmdb.title} />
							{/if}
							<div class="program-header-text">
								<h3 class="program-title">{tmdb.title}</h3>
								{#if tmdb.tagline}
									<p class="tagline">{tmdb.tagline}</p>
								{/if}
								<div class="meta-row">
									{#if tmdb.vote_average}
										<span class="meta-item">
											<span class="meta-label">{$_('insights.rating', { default: 'Rating' })}:</span>
											{tmdb.vote_average.toFixed(1)}/10
										</span>
									{/if}
									{#if tmdb.release_date || tmdb.first_air_date}
										<span class="meta-item">{(tmdb.release_date ?? tmdb.first_air_date ?? '').slice(0, 4)}</span>
									{/if}
									{#if tmdb.runtime_minutes}
										<span class="meta-item">{$_('insights.runtime', { values: { minutes: tmdb.runtime_minutes }, default: `${tmdb.runtime_minutes} min` })}</span>
									{:else if tmdb.number_of_seasons}
										<span class="meta-item">{$_('insights.seasons', { values: { count: tmdb.number_of_seasons }, default: `${tmdb.number_of_seasons} seasons` })}</span>
									{/if}
								</div>
								{#if tmdb.genres.length > 0}
									<div class="genre-pills">
										{#each tmdb.genres as genre (genre)}
											<span class="genre-pill">{genre}</span>
										{/each}
									</div>
								{/if}
							</div>
						</div>

						{#if tmdb.overview}
							<p class="overview">{tmdb.overview}</p>
						{/if}

						{#if tmdb.episode_name}
							<div class="episode-section">
								{#if tmdb.episode_still_url}
									<img class="episode-still" src={tmdb.episode_still_url} alt={tmdb.episode_name} />
								{/if}
								<div class="episode-text">
									<h4 class="section-heading">
										{#if tmdb.episode_number}
											{$_('insights.episode_heading', { values: { number: tmdb.episode_number }, default: `Episode ${tmdb.episode_number}` })}
										{:else}
											{$_('insights.episode', { default: 'Episode' })}
										{/if}
									</h4>
									<p class="episode-title">{tmdb.episode_name}</p>
									{#if tmdb.episode_air_date}
										<p class="episode-air-date">{tmdb.episode_air_date}</p>
									{/if}
									{#if tmdb.episode_overview}
										<p class="overview">{tmdb.episode_overview}</p>
									{/if}
								</div>
							</div>
						{/if}

						{#if tmdb.cast.length > 0}
							<div class="cast-section">
								<h4 class="section-heading">{$_('insights.cast', { default: 'Cast' })}</h4>
								<div class="cast-chips">
									{#each tmdb.cast as member (member.name)}
										<div class="cast-chip">
											{#if member.profile_url}
												<img class="cast-avatar" src={member.profile_url} alt={member.name} />
											{:else}
												<span class="cast-avatar cast-avatar-fallback">{member.name.charAt(0).toUpperCase()}</span>
											{/if}
											<div class="cast-names">
												<span class="cast-name">{member.name}</span>
												{#if member.character}
													<span class="cast-character">{member.character}</span>
												{/if}
											</div>
										</div>
									{/each}
								</div>
							</div>
						{/if}
					</div>
				{:else if data && !data.tmdb_configured}
					<div class="empty-state">{$_('insights.tmdb_not_configured', { default: 'Add a TMDB API key in Settings → Integrations to see show/movie details.' })}</div>
				{:else}
					<div class="empty-state">{$_('insights.no_match', { default: 'No match found on TMDB.' })}</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.insights-modal-overlay {
		position: fixed;
		inset: 0;
		z-index: 9999;
		background: rgba(0, 0, 0, 0.78);
		backdrop-filter: blur(8px);
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		pointer-events: auto;
	}

	.insights-modal-card {
		background: rgba(26, 26, 32, 0.98);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.85rem;
		width: 100%;
		max-width: 32rem;
		max-height: 85vh;
		box-shadow: 0 16px 48px rgba(0, 0, 0, 0.85);
		color: #ffffff;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		animation: modal-pop 0.15s ease;
	}

	@keyframes modal-pop {
		from { opacity: 0; transform: scale(0.95); }
		to { opacity: 1; transform: scale(1); }
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		flex-shrink: 0;
	}

	.header-title {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.1rem;
		font-weight: 600;
	}

	.close-btn {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.6);
		font-size: 1.25rem;
		cursor: pointer;
		padding: 0.25rem 0.5rem;
		border-radius: 0.25rem;
	}

	.close-btn:hover {
		color: #ffffff;
		background: rgba(255, 255, 255, 0.1);
	}

	.modal-body {
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
		overflow-y: auto;
	}

	.loading-state,
	.empty-state {
		font-size: 0.9rem;
		color: rgba(255, 255, 255, 0.65);
		text-align: center;
		padding: 1.5rem 0.5rem;
	}

	.error-banner {
		background: rgba(239, 68, 68, 0.2);
		border: 1px solid rgba(239, 68, 68, 0.4);
		color: #fca5a5;
		padding: 0.5rem 0.75rem;
		border-radius: 0.4rem;
		font-size: 0.85rem;
	}

	/* Sports */
	.status-pill {
		align-self: flex-start;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.2rem 0.55rem;
		border-radius: 0.3rem;
		background: rgba(255, 255, 255, 0.15);
		color: rgba(255, 255, 255, 0.8);
	}

	.status-pill.status-live {
		background: rgba(239, 68, 68, 0.25);
		color: #fca5a5;
	}

	.status-pill.status-finished {
		background: rgba(74, 222, 128, 0.2);
		color: #4ade80;
	}

	.scoreboard {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.team-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		background: rgba(0, 0, 0, 0.3);
		padding: 0.6rem 0.85rem;
		border-radius: 0.5rem;
	}

	.team-name {
		font-weight: 600;
		font-size: 0.95rem;
	}

	.team-score {
		font-size: 1.3rem;
		font-weight: 700;
		font-family: ui-monospace, SFMono-Regular, monospace;
	}

	.meta-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		font-size: 0.8rem;
		color: rgba(255, 255, 255, 0.7);
	}

	.live-score-note {
		margin: -0.25rem 0 0;
		font-size: 0.75rem;
		font-style: italic;
		color: rgba(255, 255, 255, 0.5);
	}

	.meta-label {
		color: rgba(255, 255, 255, 0.5);
		margin-right: 0.25rem;
	}

	/* Movies/shows */
	.program-header {
		display: flex;
		gap: 1rem;
	}

	.poster {
		width: 5.5rem;
		height: 8.25rem;
		object-fit: cover;
		border-radius: 0.4rem;
		flex-shrink: 0;
		background: rgba(255, 255, 255, 0.05);
	}

	.program-header-text {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
		min-width: 0;
	}

	.program-title {
		margin: 0;
		font-size: 1.1rem;
		font-weight: 700;
	}

	.tagline {
		margin: 0;
		font-size: 0.8rem;
		font-style: italic;
		color: rgba(255, 255, 255, 0.6);
	}

	.genre-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
	}

	.genre-pill {
		font-size: 0.7rem;
		background: rgba(56, 189, 248, 0.18);
		color: #38bdf8;
		padding: 0.15rem 0.45rem;
		border-radius: 0.25rem;
	}

	.overview {
		margin: 0;
		font-size: 0.85rem;
		line-height: 1.5;
		color: rgba(255, 255, 255, 0.85);
	}

	.episode-section {
		display: flex;
		gap: 0.85rem;
		background: rgba(0, 0, 0, 0.25);
		border-radius: 0.5rem;
		padding: 0.75rem;
	}

	.episode-still {
		width: 7rem;
		height: 3.9375rem;
		object-fit: cover;
		border-radius: 0.35rem;
		flex-shrink: 0;
		background: rgba(255, 255, 255, 0.05);
	}

	.episode-text {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		min-width: 0;
	}

	.episode-title {
		margin: 0;
		font-size: 0.9rem;
		font-weight: 600;
	}

	.episode-air-date {
		margin: 0;
		font-size: 0.75rem;
		color: rgba(255, 255, 255, 0.5);
	}

	.section-heading {
		margin: 0 0 0.5rem;
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: rgba(255, 255, 255, 0.55);
	}

	.cast-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem;
	}

	.cast-chip {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		background: rgba(0, 0, 0, 0.25);
		padding: 0.35rem 0.6rem;
		border-radius: 2rem;
		max-width: 11rem;
	}

	.cast-avatar {
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 50%;
		object-fit: cover;
		flex-shrink: 0;
	}

	.cast-avatar-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		background: #38bdf8;
		color: #000000;
		font-size: 0.75rem;
		font-weight: 700;
	}

	.cast-names {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.cast-name {
		font-size: 0.78rem;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.cast-character {
		font-size: 0.7rem;
		color: rgba(255, 255, 255, 0.55);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
</style>
