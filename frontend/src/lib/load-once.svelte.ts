// $user (and similar gated stores) resolve asynchronously — see
// +layout.svelte's gate — so a load can't just fire in onMount. This runs
// `load` the first time `condition` becomes true, and never again, without
// each call site hand-rolling its own `xInitialized` flag.
export function loadOnceWhen(condition: () => boolean, load: () => void) {
	let initialized = false;
	$effect(() => {
		if (condition() && !initialized) {
			initialized = true;
			load();
		}
	});
}
