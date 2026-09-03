<script lang="ts">
	import { getNextLoadingQuip, DEFAULT_LOADING_QUIPS } from '$lib/loading-quips';

	interface Props {
		visible?: boolean;
		intervalMs?: number;
		customQuips?: string[];
	}

	let { visible = true, intervalMs = 2800, customQuips = DEFAULT_LOADING_QUIPS }: Props = $props();

	let currentQuip = $state('');
	let quipKey = $state(0);

	$effect(() => {
		if (!currentQuip) {
			currentQuip = getNextLoadingQuip(undefined, customQuips);
		}
	});

	$effect(() => {
		if (!visible) return;

		const timer = setInterval(() => {
			currentQuip = getNextLoadingQuip(currentQuip, customQuips);
			quipKey += 1;
		}, intervalMs);

		return () => {
			clearInterval(timer);
		};
	});
</script>

{#if visible}
	<div class="loading-overlay" data-testid="loading-quip-overlay" aria-live="polite" aria-busy="true">
		<div class="spinner-container">
			<svg class="spinner-svg" viewBox="0 0 50 50" aria-hidden="true">
				<circle class="spinner-track" cx="25" cy="25" r="20" fill="none" stroke-width="4" />
				<circle class="spinner-circle" cx="25" cy="25" r="20" fill="none" stroke-width="4" />
			</svg>
		</div>
		{#key quipKey}
			<p class="quip-text" data-testid="loading-quip-text">{currentQuip || getNextLoadingQuip(undefined, customQuips)}</p>
		{/key}
	</div>
{/if}

<style>
	.loading-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 1.25rem;
		background: rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(4px);
		z-index: 104;
		pointer-events: none;
		animation: overlay-fade-in 0.2s ease-out;
		padding: 2rem;
		text-align: center;
	}

	@keyframes overlay-fade-in {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	.spinner-container {
		width: 3.5rem;
		height: 3.5rem;
		position: relative;
	}

	.spinner-svg {
		animation: rotate 1.8s linear infinite;
		width: 100%;
		height: 100%;
	}

	.spinner-track {
		stroke: rgba(255, 255, 255, 0.15);
	}

	.spinner-circle {
		stroke: #38bdf8;
		stroke-linecap: round;
		stroke-dasharray: 90, 150;
		stroke-dashoffset: 0;
		animation: dash 1.5s ease-in-out infinite;
		filter: drop-shadow(0 0 6px rgba(56, 189, 248, 0.6));
	}

	@keyframes rotate {
		100% {
			transform: rotate(360deg);
		}
	}

	@keyframes dash {
		0% {
			stroke-dasharray: 1, 150;
			stroke-dashoffset: 0;
		}
		50% {
			stroke-dasharray: 90, 150;
			stroke-dashoffset: -35;
		}
		100% {
			stroke-dasharray: 90, 150;
			stroke-dashoffset: -124;
		}
	}

	.quip-text {
		margin: 0;
		font-size: 1.1rem;
		font-weight: 500;
		color: #ffffff;
		text-shadow: 0 2px 8px rgba(0, 0, 0, 0.8), 0 0 2px rgba(0, 0, 0, 0.9);
		max-width: 28rem;
		line-height: 1.4;
		animation: quip-slide-in 0.35s cubic-bezier(0.16, 1, 0.3, 1);
	}

	@keyframes quip-slide-in {
		from {
			opacity: 0;
			transform: translateY(8px) scale(0.98);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}
</style>
