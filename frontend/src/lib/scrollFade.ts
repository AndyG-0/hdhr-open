// Svelte action: toggles `fade-top`/`fade-bottom` classes on a scrollable
// element's parent so CSS can show a gradient overlay only on the edge(s)
// that have more content to scroll to. Pass a reactive `dep` (e.g. the
// tile's summary data) so the fade recalculates once async data arrives —
// a ResizeObserver alone won't catch that, since the scroll container's own
// box size is fixed by flex layout and only its content (scrollHeight) grows.
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- dep isn't read; it only exists so Svelte re-invokes update() when it changes
export function scrollFade(node: HTMLElement, dep?: unknown) {
	const target = node.parentElement;

	function update() {
		if (!target) return;
		const { scrollTop, scrollHeight, clientHeight } = node;
		const scrollable = scrollHeight - clientHeight > 1;
		target.classList.toggle('fade-top', scrollable && scrollTop > 1);
		target.classList.toggle('fade-bottom', scrollable && scrollTop + clientHeight < scrollHeight - 1);
	}

	update();
	node.addEventListener('scroll', update, { passive: true });
	const ro = new ResizeObserver(update);
	ro.observe(node);

	return {
		update,
		destroy() {
			node.removeEventListener('scroll', update);
			ro.disconnect();
		},
	};
}
