<script lang="ts">
	import { api, type SportsFavorite, type SportsTeam } from '$lib/api';
	import { onMount } from 'svelte';
	import { SaveState } from '$lib/save-state.svelte';
	import { loadOnceWhen } from '$lib/load-once.svelte';

	interface Props {
		initialEnabled: string | null;
		initialTop25Enabled: string | null;
		initialPostseasonEnabled: string | null;
	}

	let { initialEnabled, initialTop25Enabled, initialPostseasonEnabled }: Props = $props();

	const LEAGUE_LABELS: Record<string, string> = {
		nfl: 'NFL',
		'college-football': 'College Football',
		nba: 'NBA',
		mlb: 'MLB',
		nhl: 'NHL',
		'mens-college-basketball': "Men's College Basketball",
		'eng.1': 'English Premier League',
		'esp.1': 'La Liga',
		'usa.1': 'MLS',
		'uefa.champions': 'UEFA Champions League',
	};
	function leagueLabel(league: string): string {
		return LEAGUE_LABELS[league] ?? league;
	}

	let enabled = $state(false);
	let top25Enabled = $state(false);
	let postseasonEnabled = $state(false);
	const toggleState = new SaveState();

	loadOnceWhen(
		() => initialEnabled !== null && initialTop25Enabled !== null && initialPostseasonEnabled !== null,
		() => {
			enabled = initialEnabled === 'true';
			top25Enabled = initialTop25Enabled === 'true';
			postseasonEnabled = initialPostseasonEnabled === 'true';
		},
	);

	async function saveToggles() {
		await toggleState.run(async () => {
			await api.updateSettings({
				sports_autorecord_enabled: enabled ? 'true' : 'false',
				sports_autorecord_top25_enabled: top25Enabled ? 'true' : 'false',
				sports_autorecord_postseason_enabled: postseasonEnabled ? 'true' : 'false',
			});
		}, 'Could not save sports auto-recording settings.');
	}

	let leagues = $state<string[]>([]);
	let favorites = $state<SportsFavorite[]>([]);
	let favoritesError = $state<string | null>(null);
	let removingFavoriteId = $state<string | null>(null);

	let selectedLeague = $state('');
	let leagueTeams = $state<SportsTeam[]>([]);
	let teamsLoading = $state(false);
	let teamsError = $state<string | null>(null);
	let teamSearchInput = $state('');
	let addingTeamId = $state<string | null>(null);

	onMount(() => {
		loadLeagues();
		loadFavorites();
	});

	async function loadLeagues() {
		try {
			const res = await api.getSportsLeagues();
			leagues = res.leagues;
			if (!selectedLeague && leagues.length > 0) selectedLeague = leagues[0];
		} catch {
			// leave leagues empty — the "Add a team" picker just stays unusable
		}
	}

	async function loadFavorites() {
		try {
			favorites = (await api.getSportsFavorites()).favorites;
		} catch {
			favoritesError = 'Could not load favorite teams.';
		}
	}

	async function loadTeamsForLeague(league: string) {
		teamsLoading = true;
		teamsError = null;
		leagueTeams = [];
		try {
			leagueTeams = (await api.getSportsLeagueTeams(league)).teams;
		} catch {
			teamsError = 'Could not load teams for this league right now.';
		} finally {
			teamsLoading = false;
		}
	}

	$effect(() => {
		if (selectedLeague) loadTeamsForLeague(selectedLeague);
	});

	const filteredTeams = $derived(
		teamSearchInput.trim()
			? leagueTeams.filter((t) => t.display_name.toLowerCase().includes(teamSearchInput.trim().toLowerCase()))
			: leagueTeams,
	);

	const favoritedTeamIds = $derived(
		new Set(favorites.filter((f) => f.league === selectedLeague).map((f) => f.espn_team_id)),
	);

	async function addFavorite(team: SportsTeam) {
		addingTeamId = team.id;
		favoritesError = null;
		try {
			const favorite = await api.addSportsFavorite({
				league: selectedLeague,
				espn_team_id: team.id,
				team_display_name: team.display_name,
			});
			favorites = [...favorites, favorite];
		} catch {
			favoritesError = 'Could not add this team.';
		} finally {
			addingTeamId = null;
		}
	}

	async function removeFavorite(favoriteId: string) {
		removingFavoriteId = favoriteId;
		favoritesError = null;
		try {
			await api.deleteSportsFavorite(favoriteId);
			favorites = favorites.filter((f) => f.id !== favoriteId);
		} catch {
			favoritesError = 'Could not remove this team.';
		} finally {
			removingFavoriteId = null;
		}
	}
</script>

<section class="sports-favorites-section">
	<h3>Sports auto-recording</h3>
	<label>
		<span class="checkbox-row">
			<input type="checkbox" bind:checked={enabled} />
			Automatically record upcoming games for your favorite teams
		</span>
	</label>
	<label>
		<span class="checkbox-row">
			<input type="checkbox" bind:checked={top25Enabled} disabled={!enabled} />
			Also record Top 25 college football and college basketball games
		</span>
	</label>
	<label>
		<span class="checkbox-row">
			<input type="checkbox" bind:checked={postseasonEnabled} disabled={!enabled} />
			Widen postseason coverage to non-favorited teams in your favorited leagues
		</span>
	</label>

	{#if toggleState.error}
		<p class="hint error">{toggleState.error}</p>
	{/if}
	{#if toggleState.saved}
		<p class="hint">Saved.</p>
	{/if}
	<button class="save" disabled={toggleState.saving} onclick={saveToggles}>
		{toggleState.saving ? 'Saving…' : 'Save sports auto-recording'}
	</button>

	{#if favoritesError}
		<p class="hint error">{favoritesError}</p>
	{/if}

	{#if favorites.length > 0}
		<div class="sports-favorites-container">
			<h4>Favorited teams</h4>
			<ul class="sports-favorites-list">
				{#each favorites as favorite (favorite.id)}
					<li class="sports-favorite-item">
						<span>{favorite.team_display_name ?? favorite.espn_team_id} ({leagueLabel(favorite.league)})</span>
						<button
							type="button"
							class="clear small"
							disabled={removingFavoriteId === favorite.id}
							onclick={() => removeFavorite(favorite.id)}
						>
							Remove
						</button>
					</li>
				{/each}
			</ul>
		</div>
	{/if}

	<div class="sports-search-container">
		<h4>Add a team</h4>
		<div class="sports-search-row">
			<select bind:value={selectedLeague}>
				{#each leagues as league (league)}
					<option value={league}>{leagueLabel(league)}</option>
				{/each}
			</select>
			<input type="text" bind:value={teamSearchInput} placeholder="Search teams…" />
		</div>

		{#if teamsError}
			<p class="hint error">{teamsError}</p>
		{/if}

		{#if teamsLoading}
			<p class="hint">Loading teams…</p>
		{:else if filteredTeams.length > 0}
			<div class="sports-team-results">
				{#each filteredTeams as team (team.id)}
					<div class="sports-team-result-item">
						<span>{team.display_name}</span>
						<button
							type="button"
							class="save small"
							disabled={addingTeamId === team.id || favoritedTeamIds.has(team.id)}
							onclick={() => addFavorite(team)}
						>
							{favoritedTeamIds.has(team.id) ? 'Added' : 'Add'}
						</button>
					</div>
				{/each}
			</div>
		{/if}
	</div>
</section>

<style>
	.checkbox-row {
		flex-direction: row;
		align-items: center;
		gap: 0.5rem;
		display: flex;
	}

	.checkbox-row input {
		width: auto;
	}

	.sports-favorites-container,
	.sports-search-container {
		margin-top: 0.75rem;
		padding: 0.5rem 0;
		border-top: 1px solid var(--color-border);
	}

	.sports-favorites-container h4,
	.sports-search-container h4 {
		margin: 0 0 0.5rem;
		font-size: 0.9rem;
		font-weight: 600;
	}

	.sports-favorites-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.sports-favorite-item,
	.sports-team-result-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.35rem 0.5rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.35rem;
		font-size: 0.85rem;
	}

	.sports-search-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: center;
	}

	.sports-team-results {
		margin-top: 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		max-height: 240px;
		overflow-y: auto;
	}

	:global(.sports-favorites-section) {
		column-span: all;
	}
</style>
