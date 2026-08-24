import { onMount } from 'svelte';

// Every tile fetches its summary once on mount, then again on a fixed
// interval until it unmounts — this was duplicated verbatim (refresh() +
// setInterval + clearInterval cleanup) across ~20 tile components.
export function pollWidget(refresh: () => void, intervalMs: number): void {
	onMount(() => {
		refresh();
		const interval = setInterval(refresh, intervalMs);
		return () => clearInterval(interval);
	});
}
