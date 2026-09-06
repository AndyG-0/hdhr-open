import { writable } from 'svelte/store';

// Shared open/closed state for AIAssistantDrawer, mounted once at the layout
// root — lets any entry point (nav trigger, a future Guide-page "Ask AI"
// button) open the same drawer instance instead of each owning its own.
export const aiDrawerOpen = writable(false);

export function openAIDrawer() {
	aiDrawerOpen.set(true);
}

export function closeAIDrawer() {
	aiDrawerOpen.set(false);
}

export function toggleAIDrawer() {
	aiDrawerOpen.update((open) => !open);
}
