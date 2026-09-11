import { writable, get } from 'svelte/store';
import {
	api,
	type HDHomeRunChannel,
	type HDHomeRunGuideEntry,
	type HDHomeRunTuner,
} from '$lib/api';

export type MultiViewLayout = 'side_by_side' | 'three_box' | 'quad';

export interface TunerAvailabilityResult {
	available: boolean;
	isShared: boolean;
	totalTuners: number;
	activeRecordingsCount: number;
	activeStreamsCount: number;
	sharableChannels: string[];
	explanation?: string;
}

export interface MultiViewSlot {
	id: string;
	channel: HDHomeRunChannel;
	airing?: HDHomeRunGuideEntry | null;
	watchSessionId?: string | null;
	recordingId?: string | null;
	playUrl?: string;
	streamUrl: string;
	isMuted: boolean;
	warningMessage?: string | null;
	loading: boolean;
	error?: string | null;
}

export interface MultiViewState {
	active: boolean;
	slots: MultiViewSlot[];
	activeSlotIndex: number;
	layout: MultiViewLayout;
	expandedSlotIndex: number | null;
	isAllocating: boolean;
	totalTuners: number;
	maxFeeds: number;
	tunerWarning?: string | null;
}

export const MAX_MULTIVIEW_FEEDS = 4;
const WATCH_HEARTBEAT_INTERVAL_MS = 20_000;

export function availableLayouts(maxFeeds: number = 2): MultiViewLayout[] {
	if (maxFeeds <= 2) return ['side_by_side'];
	if (maxFeeds === 3) return ['side_by_side', 'three_box'];
	return ['side_by_side', 'three_box', 'quad'];
}

export function maxSlotsForLayout(layout: MultiViewLayout): number {
	switch (layout) {
		case 'side_by_side':
			return 2;
		case 'three_box':
			return 3;
		case 'quad':
			return 4;
	}
}

export function recommendedLayout(slotCount: number, maxFeeds: number = 2): MultiViewLayout {
	const allowed = availableLayouts(maxFeeds);
	if (slotCount <= 2 || !allowed.includes('three_box')) {
		return 'side_by_side';
	}
	if (slotCount === 3 || !allowed.includes('quad')) {
		return 'three_box';
	}
	return 'quad';
}

const initialState: MultiViewState = {
	active: false,
	slots: [],
	activeSlotIndex: 0,
	layout: 'side_by_side',
	expandedSlotIndex: null,
	isAllocating: false,
	totalTuners: 2,
	maxFeeds: 2,
	tunerWarning: null,
};

export const multiview = writable<MultiViewState>(initialState);

// Tracks active heartbeat intervals by slot id
const heartbeatHandles = new Map<string, ReturnType<typeof setInterval>>();

function stopSlotHeartbeat(slotId: string) {
	const handle = heartbeatHandles.get(slotId);
	if (handle !== undefined) {
		clearInterval(handle);
		heartbeatHandles.delete(slotId);
	}
}

function startSlotHeartbeat(slotId: string, watchSessionId: string) {
	stopSlotHeartbeat(slotId);
	const handle = setInterval(() => {
		api.heartbeatWatch(watchSessionId).catch(() => {});
	}, WATCH_HEARTBEAT_INTERVAL_MS);
	heartbeatHandles.set(slotId, handle);
}

function stopAllHeartbeats() {
	for (const handle of heartbeatHandles.values()) {
		clearInterval(handle);
	}
	heartbeatHandles.clear();
}

/**
 * Loads and refreshes total physical tuner count and adapts maxFeeds / layouts.
 */
export async function initTunerCapacity(): Promise<number> {
	try {
		const info = await api.getTunerInfo();
		if (info && typeof info.tuner_count === 'number' && info.tuner_count > 0) {
			const count = info.tuner_count;
			const feeds = Math.min(MAX_MULTIVIEW_FEEDS, Math.max(1, count));
			multiview.update((state) => {
				const allowed = availableLayouts(feeds);
				const nextLayout = allowed.includes(state.layout) ? state.layout : 'side_by_side';
				return {
					...state,
					totalTuners: count,
					maxFeeds: feeds,
					layout: nextLayout,
				};
			});
			return feeds;
		}
	} catch {
		// Non-fatal
	}
	return 2;
}

/**
 * Checks physical tuner capacity and returns a warning string if all tuners are in use.
 */
export async function checkTunerCapacity(): Promise<string | null> {
	try {
		const tuners = await api.getTunerStatus();
		if (Array.isArray(tuners) && tuners.length > 0) {
			const available = tuners.filter((t: HDHomeRunTuner) => !t.in_use);
			if (available.length === 0) {
				return 'Physical tuners exhausted. Playback may fail or conflict with active recordings.';
			}
		}
	} catch {
		// Non-fatal
	}
	return null;
}

/**
 * Evaluates real-time tuner availability for a target channel, accounting for tuner sharing on active recordings/streams.
 */
export async function evaluateTunerAvailability(
	targetChannelNumber?: string,
	excludeSlotId?: string,
): Promise<TunerAvailabilityResult> {
	const currentState = get(multiview);
	let totalTuners = currentState.totalTuners || 2;
	let tuners: HDHomeRunTuner[] = [];

	try {
		const info = await api.getTunerInfo();
		if (info?.tuner_count && info.tuner_count > 0) {
			totalTuners = info.tuner_count;
		}
		const status = await api.getTunerStatus();
		if (Array.isArray(status)) {
			tuners = status;
		}
	} catch {
		// Fallback
	}

	const activeRecordings: { channel: string; title: string }[] = [];
	const activeStreams: { channel: string; viewer: string }[] = [];
	const sharableSet = new Set<string>();

	if (tuners.length > 0) {
		totalTuners = Math.max(totalTuners, tuners.length);
		for (const t of tuners) {
			if (t.in_use) {
				const ch = t.channel_number || (t.channel_name ? t.channel_name : 'Unknown');
				if (t.channel_number) {
					sharableSet.add(t.channel_number);
				}
				if (t.client?.is_recording || t.client?.type === 'scheduled_recording' || t.client?.recording_id) {
					const title = t.client?.name || t.channel_name || `Recording on ${ch}`;
					activeRecordings.push({ channel: ch, title });
				} else {
					const viewer = t.client?.name || 'Live TV Viewer';
					activeStreams.push({ channel: ch, viewer });
				}
			}
		}
	}

	// Also include channels currently running in other multi-view slots (excluding the one being added/replaced)
	for (const s of currentState.slots) {
		if (s.id !== excludeSlotId && !s.error && s.channel?.channel_number) {
			sharableSet.add(s.channel.channel_number);
		}
	}

	const inUseCount = tuners.filter((t) => t.in_use).length;
	const freeTuners = Math.max(0, totalTuners - inUseCount);
	const sharableChannels = Array.from(sharableSet);
	const isTargetShared = Boolean(targetChannelNumber && sharableSet.has(targetChannelNumber));

	if (isTargetShared || freeTuners > 0) {
		return {
			available: true,
			isShared: isTargetShared,
			totalTuners,
			activeRecordingsCount: activeRecordings.length,
			activeStreamsCount: activeStreams.length,
			sharableChannels,
		};
	}

	// All physical tuners in use and target channel requires a new tuner
	let explanation = `All ${totalTuners} tuners are currently in use.`;
	const breakdownParts: string[] = [];
	if (activeRecordings.length > 0) {
		const recDesc = activeRecordings
			.map((r) => `${r.title} (Ch ${r.channel})`)
			.join(', ');
		breakdownParts.push(`${activeRecordings.length} recording: ${recDesc}`);
	}
	if (activeStreams.length > 0) {
		const streamDesc = activeStreams
			.map((s) => `Ch ${s.channel} (${s.viewer})`)
			.join(', ');
		breakdownParts.push(`${activeStreams.length} streaming: ${streamDesc}`);
	}

	if (breakdownParts.length > 0) {
		explanation += ` Currently: ${breakdownParts.join('; ')}.`;
	}

	if (activeRecordings.length > 0) {
		const recChannels = activeRecordings.map((r) => `Ch ${r.channel}`).join(', ');
		explanation += ` You can watch ${recChannels} without consuming another tuner, or close an active feed.`;
	} else {
		explanation += ' Close an active feed to free up a tuner.';
	}

	return {
		available: false,
		isShared: false,
		totalTuners,
		activeRecordingsCount: activeRecordings.length,
		activeStreamsCount: activeStreams.length,
		sharableChannels,
		explanation,
	};
}

/**
 * Adds a new feed to the multi-view session.
 */
export async function addFeed(
	channel: HDHomeRunChannel,
	airing?: HDHomeRunGuideEntry | null,
): Promise<string> {
	const currentState = get(multiview);
	const maxFeeds = currentState.maxFeeds || 2;
	if (currentState.slots.length >= maxFeeds) {
		throw new Error(`Maximum of ${maxFeeds} concurrent feeds reached.`);
	}

	const slotId = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `slot_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
	const isFirstSlot = currentState.slots.length === 0;
	const isMuted = !isFirstSlot;

	const fallbackPlayUrl = channel.playback_url ?? `/auto/v${channel.channel_number}`;
	const fallbackStreamUrl = api.hdhomerunPlaybackUrl(fallbackPlayUrl);

	const initialSlot: MultiViewSlot = {
		id: slotId,
		channel,
		airing: airing ?? channel.now,
		playUrl: fallbackPlayUrl,
		streamUrl: fallbackStreamUrl,
		isMuted,
		loading: true,
	};

	const newSlotCount = currentState.slots.length + 1;
	const nextLayout = newSlotCount > maxSlotsForLayout(currentState.layout)
		? recommendedLayout(newSlotCount, maxFeeds)
		: currentState.layout;

	multiview.update((state) => ({
		...state,
		active: true,
		isAllocating: true,
		layout: nextLayout,
		activeSlotIndex: isFirstSlot ? 0 : state.activeSlotIndex,
		slots: [...state.slots, initialSlot],
	}));

	// Evaluate tuner availability and check for active recording / sharing
	const tunerAvail = await evaluateTunerAvailability(channel.channel_number, slotId);
	const tunerWarning = !tunerAvail.available ? tunerAvail.explanation : (await checkTunerCapacity());

	if (!tunerAvail.available) {
		multiview.update((state) => {
			const idx = state.slots.findIndex((s) => s.id === slotId);
			if (idx === -1) return { ...state, isAllocating: false };
			const updatedSlots = [...state.slots];
			updatedSlots[idx] = {
				...updatedSlots[idx],
				loading: false,
				error: tunerAvail.explanation,
				warningMessage: tunerAvail.explanation,
			};
			return {
				...state,
				isAllocating: false,
				tunerWarning,
				slots: updatedSlots,
			};
		});
		return slotId;
	}

	let watchSessionId: string | null = null;
	let recordingId: string | null = null;
	let finalPlayUrl = fallbackPlayUrl;
	let finalStreamUrl = fallbackStreamUrl;

	try {
		const watchRes = await api.startWatch(channel.channel_number);
		if (watchRes?.recording_id && watchRes.session_id) {
			watchSessionId = watchRes.session_id;
			recordingId = watchRes.recording_id;
			finalPlayUrl = watchRes.play_url ?? fallbackPlayUrl;
			finalStreamUrl = api.hdhomerunRecordingStreamUrl(finalPlayUrl, { recordingId });
			startSlotHeartbeat(slotId, watchSessionId);
		}
	} catch {
		// Fall back to direct channel playback
	}

	multiview.update((state) => {
		const idx = state.slots.findIndex((s) => s.id === slotId);
		if (idx === -1) return { ...state, isAllocating: false };

		const updatedSlots = [...state.slots];
		updatedSlots[idx] = {
			...updatedSlots[idx],
			watchSessionId,
			recordingId,
			playUrl: finalPlayUrl,
			streamUrl: finalStreamUrl,
			warningMessage: tunerWarning,
			loading: false,
		};

		return {
			...state,
			isAllocating: false,
			tunerWarning,
			slots: updatedSlots,
		};
	});

	return slotId;
}

/**
 * Stops a slot's heartbeat and terminates its watch session on the backend.
 */
function teardownSlot(slot: MultiViewSlot): void {
	stopSlotHeartbeat(slot.id);
	if (slot.watchSessionId) {
		api.stopWatch(slot.watchSessionId);
	}
}

/**
 * Removes a feed by index.
 */
export function removeFeed(index: number): void {
	const currentState = get(multiview);
	if (index < 0 || index >= currentState.slots.length) return;

	teardownSlot(currentState.slots[index]);

	const remainingSlots = currentState.slots.filter((_, i) => i !== index);

	if (remainingSlots.length === 0) {
		closeAll();
		return;
	}

	let nextActiveIndex = currentState.activeSlotIndex;
	if (nextActiveIndex >= remainingSlots.length) {
		nextActiveIndex = remainingSlots.length - 1;
	} else if (index < nextActiveIndex) {
		nextActiveIndex -= 1;
	}

	// Auto adapt layout down if slots decreased
	let nextLayout = currentState.layout;
	if (remainingSlots.length <= 2 && currentState.layout !== 'side_by_side') {
		nextLayout = 'side_by_side';
	} else if (remainingSlots.length === 3 && currentState.layout === 'quad') {
		nextLayout = 'three_box';
	}

	// Update mute states based on nextActiveIndex
	const updatedSlots = remainingSlots.map((s, i) => ({
		...s,
		isMuted: i !== nextActiveIndex,
	}));

	multiview.set({
		...currentState,
		slots: updatedSlots,
		activeSlotIndex: nextActiveIndex,
		layout: nextLayout,
		expandedSlotIndex: currentState.expandedSlotIndex === index ? null : currentState.expandedSlotIndex,
	});
}

/**
 * Replaces the channel in a specific slot without closing the slot or disturbing others.
 */
export async function replaceFeed(
	index: number,
	channel: HDHomeRunChannel,
	airing?: HDHomeRunGuideEntry | null,
): Promise<void> {
	const currentState = get(multiview);
	if (index < 0 || index >= currentState.slots.length) return;

	const oldSlot = currentState.slots[index];
	stopSlotHeartbeat(oldSlot.id);
	if (oldSlot.watchSessionId) {
		api.stopWatch(oldSlot.watchSessionId);
	}

	const wasMuted = oldSlot.isMuted;
	const fallbackPlayUrl = channel.playback_url ?? `/auto/v${channel.channel_number}`;
	const fallbackStreamUrl = api.hdhomerunPlaybackUrl(fallbackPlayUrl);

	multiview.update((state) => {
		const updated = [...state.slots];
		updated[index] = {
			...updated[index],
			channel,
			airing: airing ?? channel.now,
			playUrl: fallbackPlayUrl,
			streamUrl: fallbackStreamUrl,
			watchSessionId: null,
			recordingId: null,
			isMuted: wasMuted,
			loading: true,
			error: null,
			warningMessage: null,
		};
		return { ...state, slots: updated };
	});

	const tunerAvail = await evaluateTunerAvailability(channel.channel_number, oldSlot.id);
	const tunerWarning = !tunerAvail.available ? tunerAvail.explanation : (await checkTunerCapacity());

	if (!tunerAvail.available) {
		multiview.update((state) => {
			if (index >= state.slots.length) return state;
			const updated = [...state.slots];
			updated[index] = {
				...updated[index],
				loading: false,
				error: tunerAvail.explanation,
				warningMessage: tunerAvail.explanation,
			};
			return {
				...state,
				tunerWarning,
				slots: updated,
			};
		});
		return;
	}

	let watchSessionId: string | null = null;
	let recordingId: string | null = null;
	let finalPlayUrl = fallbackPlayUrl;
	let finalStreamUrl = fallbackStreamUrl;

	try {
		const watchRes = await api.startWatch(channel.channel_number);
		if (watchRes?.recording_id && watchRes.session_id) {
			watchSessionId = watchRes.session_id;
			recordingId = watchRes.recording_id;
			finalPlayUrl = watchRes.play_url ?? fallbackPlayUrl;
			finalStreamUrl = api.hdhomerunRecordingStreamUrl(finalPlayUrl, { recordingId });
			startSlotHeartbeat(oldSlot.id, watchSessionId);
		}
	} catch {
		// Fallback
	}

	multiview.update((state) => {
		if (index >= state.slots.length) return state;
		const updated = [...state.slots];
		updated[index] = {
			...updated[index],
			watchSessionId,
			recordingId,
			playUrl: finalPlayUrl,
			streamUrl: finalStreamUrl,
			warningMessage: tunerWarning,
			loading: false,
		};
		return { ...state, slots: updated };
	});
}

/**
 * Sets the active audio focus to a given slot index.
 */
export function setAudioSlot(index: number): void {
	const currentState = get(multiview);
	if (index < 0 || index >= currentState.slots.length) return;

	const updatedSlots = currentState.slots.map((s, i) => ({
		...s,
		isMuted: i !== index,
	}));

	multiview.update((state) => ({
		...state,
		activeSlotIndex: index,
		slots: updatedSlots,
	}));
}

/**
 * Swaps two slots in the grid (e.g. promoting any slot to Hero Slot 0).
 */
export function swapSlots(fromIndex: number, toIndex: number): void {
	const currentState = get(multiview);
	if (
		fromIndex < 0 ||
		fromIndex >= currentState.slots.length ||
		toIndex < 0 ||
		toIndex >= currentState.slots.length ||
		fromIndex === toIndex
	) {
		return;
	}

	const updatedSlots = [...currentState.slots];
	const temp = updatedSlots[fromIndex];
	updatedSlots[fromIndex] = updatedSlots[toIndex];
	updatedSlots[toIndex] = temp;

	let nextActiveIndex = currentState.activeSlotIndex;
	if (currentState.activeSlotIndex === fromIndex) {
		nextActiveIndex = toIndex;
	} else if (currentState.activeSlotIndex === toIndex) {
		nextActiveIndex = fromIndex;
	}

	// Reapply mute states
	const finalSlots = updatedSlots.map((s, i) => ({
		...s,
		isMuted: i !== nextActiveIndex,
	}));

	multiview.update((state) => ({
		...state,
		slots: finalSlots,
		activeSlotIndex: nextActiveIndex,
	}));
}

/**
 * Sets the presentation layout. If the new layout has less capacity than the
 * number of active slots, the excess slots (last first) are removed and their
 * watch sessions terminated the same way removeFeed() does.
 */
export function setLayout(layout: MultiViewLayout): void {
	const currentState = get(multiview);
	const capacity = maxSlotsForLayout(layout);

	if (currentState.slots.length <= capacity) {
		multiview.update((state) => ({ ...state, layout }));
		return;
	}

	const keptSlots = currentState.slots.slice(0, capacity);
	const removedSlots = currentState.slots.slice(capacity);
	for (const slot of removedSlots) {
		teardownSlot(slot);
	}

	const nextActiveIndex = Math.min(currentState.activeSlotIndex, keptSlots.length - 1);
	const updatedSlots = keptSlots.map((s, i) => ({
		...s,
		isMuted: i !== nextActiveIndex,
	}));

	multiview.set({
		...currentState,
		layout,
		slots: updatedSlots,
		activeSlotIndex: nextActiveIndex,
		expandedSlotIndex:
			currentState.expandedSlotIndex !== null && currentState.expandedSlotIndex >= capacity
				? null
				: currentState.expandedSlotIndex,
	});
}

/**
 * Expands a single tile to fullscreen, or collapses back to grid when passed null.
 */
export function expandSlot(index: number | null): void {
	multiview.update((state) => {
		if (index !== null && index >= 0 && index < state.slots.length) {
			return {
				...state,
				expandedSlotIndex: index,
				activeSlotIndex: index,
				slots: state.slots.map((s, i) => ({
					...s,
					isMuted: i !== index,
				})),
			};
		}
		return {
			...state,
			expandedSlotIndex: null,
		};
	});
}

/**
 * Closes all feeds and resets the multi-view state.
 */
export function closeAll(): void {
	const currentState = get(multiview);
	stopAllHeartbeats();

	for (const slot of currentState.slots) {
		if (slot.watchSessionId) {
			api.stopWatch(slot.watchSessionId);
		}
	}

	multiview.set(initialState);
}

// Global pagehide listener for clean teardown of watch sessions on tab close/unload
if (typeof window !== 'undefined') {
	window.addEventListener('pagehide', () => {
		const currentState = get(multiview);
		stopAllHeartbeats();
		for (const slot of currentState.slots) {
			if (slot.watchSessionId) {
				api.stopWatch(slot.watchSessionId);
			}
		}
	});
}
