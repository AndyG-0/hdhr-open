<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { _ } from 'svelte-i18n';
	import {
		multiview,
		addFeed,
		removeFeed,
		replaceFeed,
		setAudioSlot,
		swapSlots,
		setLayout,
		expandSlot,
		closeAll,
		maxSlotsForLayout,
		availableLayouts,
		initTunerCapacity,
	} from '$lib/stores/multiview';
	import { api, type HDHomeRunChannel } from '$lib/api';
	import PlayerIcon from '../icons/PlayerIcon.svelte';
	import PlayerVolumeControl from '../PlayerVolumeControl.svelte';
	import PlayerChannelDrawer from '../PlayerChannelDrawer.svelte';
	import MultiViewSlotTile from './MultiViewSlotTile.svelte';
	import MultiViewEmptyTile from './MultiViewEmptyTile.svelte';

	interface Props {
		channels?: HDHomeRunChannel[];
		favoriteChannels?: Set<string>;
		onClose?: () => void;
	}

	let {
		channels = [],
		favoriteChannels = new Set<string>(),
		onClose = () => closeAll(),
	}: Props = $props();

	let internalChannels = $state<HDHomeRunChannel[]>([]);
	let internalFavoriteChannels = $state<Set<string>>(new Set());

	$effect(() => {
		if (channels.length > 0) {
			internalChannels = channels;
		}
	});

	$effect(() => {
		if (favoriteChannels.size > 0) {
			internalFavoriteChannels = favoriteChannels;
		}
	});

	let showChannelDrawer = $state(false);
	let targetSlotForChannelChange = $state<number | null>(null);
	let volume = $state(1.0);
	let isMutedAll = $state(false);

	// Load volume setting
	if (typeof localStorage !== 'undefined') {
		try {
			const savedVol = localStorage.getItem('hdhr_player_volume');
			if (savedVol !== null) volume = Math.max(0, Math.min(1, Number(savedVol)));
		} catch {
			// ignore
		}
	}

	function handleVolumeChange(newVol: number) {
		volume = newVol;
		if (typeof localStorage !== 'undefined') {
			try {
				localStorage.setItem('hdhr_player_volume', String(newVol));
			} catch {
				// ignore
			}
		}
	}

	function handleMuteToggle() {
		isMutedAll = !isMutedAll;
		if (isMutedAll) {
			// Mute active slot
			if ($multiview.slots.length > 0) {
				setAudioSlot(-1);
			}
		} else {
			// Unmute active slot
			setAudioSlot($multiview.activeSlotIndex >= 0 ? $multiview.activeSlotIndex : 0);
		}
	}

	let activeTunerChannels = $state<{ recording: Set<string>; streaming: Set<string> }>({
		recording: new Set(),
		streaming: new Set(),
	});

	async function refreshDrawerTunerBadges() {
		try {
			const tuners = await api.getTunerStatus();
			const rec = new Set<string>();
			const strm = new Set<string>();
			if (Array.isArray(tuners)) {
				for (const t of tuners) {
					if (t.in_use && t.channel_number) {
						if (t.client?.is_recording || t.client?.type === 'scheduled_recording' || t.client?.recording_id) {
							rec.add(t.channel_number);
						} else {
							strm.add(t.channel_number);
						}
					}
				}
			}
			activeTunerChannels = { recording: rec, streaming: strm };
		} catch {
			// ignore
		}
	}

	function handleOpenAddFeed() {
		targetSlotForChannelChange = null;
		showChannelDrawer = true;
		refreshDrawerTunerBadges().catch(() => {});
	}

	function handleOpenChangeChannel(index: number) {
		targetSlotForChannelChange = index;
		showChannelDrawer = true;
		refreshDrawerTunerBadges().catch(() => {});
	}

	async function handleChannelSelected(channel: HDHomeRunChannel) {
		showChannelDrawer = false;
		if (targetSlotForChannelChange !== null) {
			await replaceFeed(targetSlotForChannelChange, channel);
			targetSlotForChannelChange = null;
		} else {
			try {
				await addFeed(channel);
			} catch (err) {
				console.error('Failed to add feed:', err);
			}
		}
	}

	function handleKeyDown(e: KeyboardEvent) {
		// Ignore typing in input elements
		if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

		if (e.key === 'Escape') {
			if (showChannelDrawer) {
				showChannelDrawer = false;
			} else if ($multiview.expandedSlotIndex !== null) {
				expandSlot(null);
			} else {
				onClose();
			}
			return;
		}

		if (e.key >= '1' && e.key <= '4') {
			const targetIdx = parseInt(e.key, 10) - 1;
			if (targetIdx < $multiview.slots.length) {
				setAudioSlot(targetIdx);
			}
			return;
		}

		if (e.key === 'm' || e.key === 'M') {
			handleMuteToggle();
			return;
		}

		if (e.key === 'f' || e.key === 'F') {
			if ($multiview.expandedSlotIndex !== null) {
				expandSlot(null);
			} else if ($multiview.slots.length > 0) {
				expandSlot($multiview.activeSlotIndex);
			}
			return;
		}
	}

	const maxSlots = $derived(maxSlotsForLayout($multiview.layout));
	const maxAllowedSlots = $derived(Math.min(maxSlots, $multiview.maxFeeds));
	const emptySlotsCount = $derived(Math.max(0, maxAllowedSlots - $multiview.slots.length));
	const canAddFeed = $derived($multiview.slots.length < $multiview.maxFeeds);
	const allowedLayouts = $derived(availableLayouts($multiview.maxFeeds));

	onMount(() => {
		const prevOverflow = typeof document !== 'undefined' ? document.body.style.overflow : '';
		if (typeof document !== 'undefined') {
			document.body.style.overflow = 'hidden';
		}
		window.addEventListener('keydown', handleKeyDown);
		initTunerCapacity().catch(() => {});

		if (internalChannels.length === 0) {
			api.getHDHomeRunChannels()
				.then((res) => {
					if (Array.isArray(res?.channels) && res.channels.length > 0) {
						internalChannels = res.channels;
					}
				})
				.catch(() => {});
		}

		if (internalFavoriteChannels.size === 0) {
			api.getNetworkIntegration('hdhomerun')
				.then((integration) => {
					if (Array.isArray(integration?.settings?.favorite_channels)) {
						internalFavoriteChannels = new Set(integration.settings.favorite_channels as string[]);
					}
				})
				.catch(() => {});
		}

		return () => {
			if (typeof document !== 'undefined') {
				document.body.style.overflow = prevOverflow;
			}
			window.removeEventListener('keydown', handleKeyDown);
		};
	});

	onDestroy(() => {
		// Keep session clean if unmounted
	});
</script>

<div class="multiview-container" role="application" aria-label="Multi-View Player">
	<!-- Top Multi-View Toolbar -->
	<header class="multiview-toolbar">
		<div class="toolbar-left">
			<button
				type="button"
				class="toolbar-btn back-btn"
				onclick={onClose}
				aria-label={$_('multiview.close_all', { default: 'Close Multi-View' })}
				title={$_('multiview.close_all', { default: 'Close Multi-View' })}
			>
				<PlayerIcon name="back" size={22} />
			</button>

			<div class="title-cluster">
				<div class="main-title">
					<PlayerIcon name="multiview" size={20} class="multiview-title-icon" />
					<span>{$_('multiview.title', { default: 'Multi-View Playback' })}</span>
				</div>
				<div class="sub-meta">
					<span class="feed-count-badge">
						{$multiview.slots.length} of {$multiview.maxFeeds} Feeds Active
					</span>
					{#if $multiview.tunerWarning}
						<span class="tuner-warning-chip" title={$multiview.tunerWarning}>
							⚠️ Tuners Busy
						</span>
					{/if}
				</div>
			</div>
		</div>

		<div class="toolbar-center">
			<!-- Layout Selector Buttons -->
			<div class="layout-picker" role="radiogroup" aria-label="Layout Selection">
				{#if allowedLayouts.includes('side_by_side')}
					<button
						type="button"
						class="layout-btn"
						class:active={$multiview.layout === 'side_by_side'}
						onclick={() => setLayout('side_by_side')}
						aria-label={$_('multiview.layout_2up', { default: '2-Up Split' })}
						title={$_('multiview.layout_2up', { default: '2-Up Split' })}
					>
						<PlayerIcon name="grid-2" size={18} />
						<span class="layout-btn-text">2-Up</span>
					</button>
				{/if}

				{#if allowedLayouts.includes('three_box')}
					<button
						type="button"
						class="layout-btn"
						class:active={$multiview.layout === 'three_box'}
						onclick={() => setLayout('three_box')}
						aria-label={$_('multiview.layout_3up', { default: '3-Up Hero' })}
						title={$_('multiview.layout_3up', { default: '3-Up Hero' })}
					>
						<PlayerIcon name="grid-3" size={18} />
						<span class="layout-btn-text">3-Up</span>
					</button>
				{/if}

				{#if allowedLayouts.includes('quad')}
					<button
						type="button"
						class="layout-btn"
						class:active={$multiview.layout === 'quad'}
						onclick={() => setLayout('quad')}
						aria-label={$_('multiview.layout_quad', { default: 'Quad Grid' })}
						title={$_('multiview.layout_quad', { default: 'Quad Grid' })}
					>
						<PlayerIcon name="grid-4" size={18} />
						<span class="layout-btn-text">Quad</span>
					</button>
				{/if}
			</div>
		</div>

		<div class="toolbar-right">
			{#if canAddFeed}
				<button
					type="button"
					class="add-feed-btn"
					onclick={handleOpenAddFeed}
					aria-label={$_('multiview.add_feed', { default: 'Add Feed' })}
				>
					<PlayerIcon name="plus" size={18} />
					<span>{$_('multiview.add_feed', { default: 'Add Feed' })}</span>
				</button>
			{/if}

			<div class="volume-wrapper">
				<PlayerVolumeControl
					{volume}
					muted={$multiview.activeSlotIndex === -1 || isMutedAll}
					onVolumeChange={handleVolumeChange}
					onMuteToggle={handleMuteToggle}
				/>
			</div>

			<button
				type="button"
				class="toolbar-btn close-all-btn"
				onclick={onClose}
				aria-label={$_('multiview.close_all', { default: 'Close Multi-View' })}
				title={$_('multiview.close_all', { default: 'Close Multi-View' })}
			>
				<PlayerIcon name="close" size={20} />
			</button>
		</div>
	</header>

	<!-- Main Multi-View Grid Content Area -->
	<main class="grid-viewport">
		{#if $multiview.expandedSlotIndex !== null && $multiview.slots[$multiview.expandedSlotIndex]}
			<!-- Single Expanded Fullscreen Tile -->
			{@const expIdx = $multiview.expandedSlotIndex}
			{@const expSlot = $multiview.slots[expIdx]}
			<div class="expanded-tile-wrapper">
				<div class="expanded-collapse-bar">
					<button
						type="button"
						class="collapse-btn"
						onclick={() => expandSlot(null)}
						aria-label="Collapse to Grid"
					>
						<PlayerIcon name="fullscreen-exit" size={18} />
						<span>Collapse to Grid (Esc)</span>
					</button>
				</div>
				<MultiViewSlotTile
					slot={expSlot}
					index={expIdx}
					isAudioActive={true}
					isExpanded={true}
					{volume}
					onSelectAudio={() => setAudioSlot(expIdx)}
					onMakeHero={() => swapSlots(expIdx, 0)}
					onChangeChannel={() => handleOpenChangeChannel(expIdx)}
					onToggleFullscreen={() => expandSlot(null)}
					onClose={() => {
						expandSlot(null);
						removeFeed(expIdx);
					}}
				/>
			</div>
		{:else}
			<!-- Multi-Tile Grid Container -->
			<div
				class="slots-grid"
				class:layout-side-by-side={$multiview.layout === 'side_by_side'}
				class:layout-three-box={$multiview.layout === 'three_box'}
				class:layout-quad={$multiview.layout === 'quad'}
			>
				{#each $multiview.slots as slot, index (slot.id)}
					<div
						class="grid-cell"
						class:hero-cell={$multiview.layout === 'three_box' && index === 0}
					>
						<MultiViewSlotTile
							{slot}
							{index}
							isAudioActive={$multiview.activeSlotIndex === index && !isMutedAll}
							isHero={$multiview.layout === 'three_box' && index === 0}
							canMakeHero={$multiview.layout === 'three_box' && index !== 0}
							isExpanded={false}
							{volume}
							onSelectAudio={() => setAudioSlot(index)}
							onMakeHero={() => swapSlots(index, 0)}
							onChangeChannel={() => handleOpenChangeChannel(index)}
							onToggleFullscreen={() => expandSlot(index)}
							onClose={() => removeFeed(index)}
						/>
					</div>
				{/each}

				<!-- Empty Placeholder Tiles up to layout max capacity -->
				{#each Array.from(Array(emptySlotsCount).keys()) as emptyIndex (emptyIndex)}
					{@const targetSlotNum = $multiview.slots.length + emptyIndex}
					<div class="grid-cell empty-cell">
						<MultiViewEmptyTile
							slotIndex={targetSlotNum}
							onAddFeed={handleOpenAddFeed}
						/>
					</div>
				{/each}
			</div>
		{/if}
	</main>

	<!-- In-Player Channel Drawer -->
	{#if showChannelDrawer}
		<PlayerChannelDrawer
			channels={internalChannels}
			favoriteChannels={internalFavoriteChannels}
			activeChannels={activeTunerChannels.streaming}
			recordingChannels={activeTunerChannels.recording}
			currentChannelNumber={targetSlotForChannelChange !== null && $multiview.slots[targetSlotForChannelChange]
				? $multiview.slots[targetSlotForChannelChange].channel.channel_number
				: null}
			onSelect={handleChannelSelected}
			onClose={() => (showChannelDrawer = false)}
		/>
	{/if}
</div>

<style>
	.multiview-container {
		position: fixed;
		inset: 0;
		width: 100vw;
		height: 100vh;
		background: #09090b;
		z-index: 100;
		display: flex;
		flex-direction: column;
		color: #ffffff;
		user-select: none;
		overflow: hidden;
	}

	/* Top Toolbar */
	.multiview-toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 1.25rem;
		background: rgba(18, 18, 22, 0.95);
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
		backdrop-filter: blur(12px);
		z-index: 20;
		flex-shrink: 0;
		gap: 1rem;
	}

	.toolbar-left {
		display: flex;
		align-items: center;
		gap: 0.85rem;
		min-width: 0;
	}

	.toolbar-btn {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.85);
		padding: 0.5rem;
		border-radius: 50%;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.toolbar-btn:hover {
		background: rgba(255, 255, 255, 0.15);
		color: #ffffff;
	}

	.title-cluster {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		min-width: 0;
	}

	.main-title {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		font-size: 1.05rem;
		font-weight: 700;
		color: #ffffff;
		white-space: nowrap;
	}

	:global(.multiview-title-icon) {
		color: #38bdf8;
	}

	.sub-meta {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.feed-count-badge {
		font-size: 0.75rem;
		color: rgba(255, 255, 255, 0.55);
		font-weight: 500;
	}

	.tuner-warning-chip {
		background: rgba(234, 179, 8, 0.2);
		color: #facc15;
		border: 1px solid rgba(234, 179, 8, 0.4);
		font-size: 0.7rem;
		font-weight: 600;
		padding: 0.05rem 0.35rem;
		border-radius: 0.25rem;
	}

	/* Layout Selector */
	.toolbar-center {
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.layout-picker {
		display: flex;
		align-items: center;
		background: rgba(255, 255, 255, 0.08);
		border-radius: 0.6rem;
		padding: 0.2rem;
		gap: 0.2rem;
		border: 1px solid rgba(255, 255, 255, 0.1);
	}

	.layout-btn {
		display: flex;
		align-items: center;
		gap: 0.35rem;
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.7);
		padding: 0.35rem 0.65rem;
		border-radius: 0.45rem;
		font-size: 0.8rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s ease, color 0.15s ease;
	}

	.layout-btn:hover {
		color: #ffffff;
		background: rgba(255, 255, 255, 0.1);
	}

	.layout-btn.active {
		background: #38bdf8;
		color: #000000;
	}

	.layout-btn-text {
		font-size: 0.8rem;
	}

	/* Toolbar Right */
	.toolbar-right {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-shrink: 0;
	}

	.add-feed-btn {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		background: rgba(56, 189, 248, 0.2);
		border: 1px solid rgba(56, 189, 248, 0.4);
		color: #38bdf8;
		padding: 0.4rem 0.85rem;
		border-radius: 0.5rem;
		font-size: 0.85rem;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.15s ease, transform 0.1s ease;
	}

	.add-feed-btn:hover {
		background: rgba(56, 189, 248, 0.35);
		color: #ffffff;
		transform: scale(1.02);
	}

	.volume-wrapper {
		display: flex;
		align-items: center;
	}

	.close-all-btn:hover {
		background: rgba(239, 68, 68, 0.25);
		color: #f87171;
	}

	/* Main Viewport & Grids */
	.grid-viewport {
		flex: 1;
		width: 100%;
		height: 100%;
		padding: 1rem;
		box-sizing: border-box;
		overflow: hidden;
		display: flex;
		position: relative;
	}

	.slots-grid {
		width: 100%;
		height: 100%;
		display: grid;
		gap: 1rem;
		box-sizing: border-box;
	}

	/* 2-Up Side-by-Side: 2 equal columns */
	.slots-grid.layout-side-by-side {
		grid-template-columns: repeat(2, 1fr);
		grid-template-rows: 1fr;
	}

	/* 3-Up Hero: Left 2fr column spans 2 rows, right 1fr column has 2 rows */
	.slots-grid.layout-three-box {
		grid-template-columns: 2fr 1fr;
		grid-template-rows: 1fr 1fr;
	}

	.hero-cell {
		grid-row: 1 / span 2;
	}

	/* Quad: 2x2 equal grid */
	.slots-grid.layout-quad {
		grid-template-columns: repeat(2, 1fr);
		grid-template-rows: repeat(2, 1fr);
	}

	.grid-cell {
		width: 100%;
		height: 100%;
		min-width: 0;
		min-height: 0;
		overflow: hidden;
		border-radius: 0.85rem;
	}

	/* Expanded Single Fullscreen View */
	.expanded-tile-wrapper {
		position: absolute;
		inset: 1rem;
		z-index: 30;
		display: flex;
		flex-direction: column;
		background: #000;
		border-radius: 0.85rem;
		overflow: hidden;
	}

	.expanded-collapse-bar {
		position: absolute;
		top: 1rem;
		left: 1rem;
		z-index: 40;
	}

	.collapse-btn {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		background: rgba(0, 0, 0, 0.75);
		border: 1px solid rgba(255, 255, 255, 0.25);
		color: #ffffff;
		padding: 0.45rem 0.85rem;
		border-radius: 0.5rem;
		font-size: 0.85rem;
		font-weight: 600;
		cursor: pointer;
		backdrop-filter: blur(8px);
		transition: background 0.15s ease;
	}

	.collapse-btn:hover {
		background: rgba(56, 189, 248, 0.35);
		border-color: #38bdf8;
	}

	/* Responsive tweaks for smaller screens */
	@media (max-width: 768px) {
		.slots-grid.layout-side-by-side,
		.slots-grid.layout-three-box,
		.slots-grid.layout-quad {
			grid-template-columns: 1fr;
			grid-template-rows: auto;
			overflow-y: auto;
		}

		.hero-cell {
			grid-row: auto;
		}

		.layout-btn-text {
			display: none;
		}
	}
</style>
