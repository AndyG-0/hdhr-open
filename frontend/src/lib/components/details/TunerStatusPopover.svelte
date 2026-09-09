<script lang="ts">
	import type { HDHomeRunTuner } from '$lib/api';
	import { _ } from 'svelte-i18n';

	interface Props {
		tuners?: HDHomeRunTuner[];
		tunerCount?: number;
		onTerminateTuner: (tuner: HDHomeRunTuner) => void;
	}

	let { tuners = [], tunerCount = 0, onTerminateTuner }: Props = $props();
</script>

<div
	class="tuner-count-container"
	tabindex="0"
	role="button"
	aria-haspopup="true"
	aria-label={$_('hdhomerun.detail.tuner_count', { values: { count: tunerCount } })}
>
	<span class="tuner-count-pill">
		{$_('hdhomerun.detail.tuner_count', { values: { count: tunerCount } })}
		{#if tuners.some((t) => t.in_use)}
			<span class="tuner-active-dot" aria-hidden="true"></span>
		{/if}
	</span>
	<div class="tuner-status-popover" role="tooltip">
		<div class="tuner-status-header">{$_('hdhomerun.detail.tuner_status_heading')}</div>
		{#if tuners.length > 0}
			<ul class="tuner-status-list">
				{#each tuners as tuner (tuner.index)}
					<li class="tuner-status-row" class:in-use={tuner.in_use}>
						<div class="tuner-status-label-group">
							<span class="tuner-status-indicator" class:active={tuner.in_use}></span>
							<span class="tuner-status-name">
								{$_('hdhomerun.detail.tuner_label', { values: { index: tuner.index } })}
							</span>
						</div>
						<div class="tuner-status-details">
							{#if tuner.in_use}
								<span class="tuner-channel">
									{#if tuner.channel_number}<span class="tuner-ch-num">{tuner.channel_number}</span>{/if}
									{#if tuner.channel_name}<span class="tuner-ch-name">{tuner.channel_name}</span>{:else}<span
											class="tuner-in-use-tag">{$_('hdhomerun.detail.tuner_in_use')}</span
										>{/if}
								</span>
								{#if tuner.client}
									<span
										class="tuner-client-badge"
										class:external={tuner.client.type === 'external'}
										class:recording={tuner.client.is_recording}
										title={tuner.client.details}
									>
										{#if tuner.client.type === 'external'}
											{$_('hdhomerun.detail.tuner_client_external', { values: { ip: tuner.client.name } })}
										{:else}
											{$_('hdhomerun.detail.tuner_client_label', { values: { name: tuner.client.name } })}
										{/if}
									</span>
								{/if}
								{#if tuner.signal_strength_percent != null}
									<span class="tuner-signal">
										{$_('hdhomerun.detail.tuner_signal', {
											values: { percent: tuner.signal_strength_percent },
										})}
									</span>
								{/if}
								<button
									type="button"
									class="tuner-terminate-btn"
									aria-label={$_('hdhomerun.detail.tuner_terminate_button')}
									onclick={(e) => {
										e.stopPropagation();
										onTerminateTuner(tuner);
									}}
								>
									{$_('hdhomerun.detail.tuner_terminate_button')}
								</button>
							{:else}
								<span class="tuner-idle">{$_('hdhomerun.detail.tuner_idle')}</span>
							{/if}
						</div>
					</li>
				{/each}
			</ul>
		{:else}
			<p class="tuner-status-empty">{$_('hdhomerun.detail.tuner_status_unavailable')}</p>
		{/if}
	</div>
</div>

<style>
	.tuner-count-container {
		position: relative;
		display: inline-flex;
		align-items: center;
		outline: none;
	}

	.tuner-count-pill {
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		border-bottom: 1px dashed var(--color-text-muted);
		transition:
			color 0.15s ease,
			border-color 0.15s ease;
	}

	.tuner-count-container:hover .tuner-count-pill,
	.tuner-count-container:focus .tuner-count-pill,
	.tuner-count-container:focus-within .tuner-count-pill {
		color: var(--color-text);
		border-color: var(--color-accent);
	}

	.tuner-active-dot {
		width: 0.45rem;
		height: 0.45rem;
		border-radius: 50%;
		background: var(--color-success, #4caf50);
		box-shadow: 0 0 4px var(--color-success, #4caf50);
	}

	.tuner-status-popover {
		position: absolute;
		top: calc(100% + 0.4rem);
		left: 0;
		z-index: 10;
		min-width: 16rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		padding: 0.6rem 0.75rem;
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
		opacity: 0;
		visibility: hidden;
		transform: translateY(4px);
		pointer-events: none;
		transition:
			opacity 0.15s ease,
			transform 0.15s ease,
			visibility 0.15s;
	}

	.tuner-count-container:hover .tuner-status-popover,
	.tuner-count-container:focus .tuner-status-popover,
	.tuner-count-container:focus-within .tuner-status-popover {
		opacity: 1;
		visibility: visible;
		transform: translateY(0);
		pointer-events: auto;
	}

	.tuner-status-header {
		font-weight: 600;
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--color-text-muted);
		margin-bottom: 0.4rem;
		border-bottom: 1px solid var(--color-border);
		padding-bottom: 0.25rem;
	}

	.tuner-status-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.tuner-status-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		font-size: 0.82rem;
		padding: 0.2rem 0;
	}

	.tuner-status-label-group {
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}

	.tuner-status-indicator {
		width: 0.45rem;
		height: 0.45rem;
		border-radius: 50%;
		background: var(--color-text-muted);
		opacity: 0.4;
	}

	.tuner-status-indicator.active {
		background: var(--color-success, #4caf50);
		opacity: 1;
		box-shadow: 0 0 5px var(--color-success, #4caf50);
	}

	.tuner-status-name {
		font-weight: 500;
		color: var(--color-text);
	}

	.tuner-status-details {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.tuner-channel {
		color: var(--color-text);
		font-weight: 500;
	}

	.tuner-ch-num {
		color: var(--color-accent);
		margin-right: 0.2rem;
	}

	.tuner-in-use-tag {
		color: var(--color-accent);
	}

	.tuner-signal {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.tuner-idle {
		color: var(--color-text-muted);
		font-style: italic;
	}

	.tuner-client-badge {
		font-size: 0.72rem;
		padding: 0.1rem 0.35rem;
		border-radius: 0.25rem;
		background: var(--color-surface-variant, rgba(255, 255, 255, 0.08));
		color: var(--color-text);
		border: 1px solid var(--color-border);
		max-width: 10rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.tuner-client-badge.external {
		color: #e5a00d;
		border-color: rgba(229, 160, 13, 0.3);
		background: rgba(229, 160, 13, 0.1);
	}

	.tuner-client-badge.recording {
		color: #e05a5a;
		border-color: rgba(224, 90, 90, 0.3);
		background: rgba(224, 90, 90, 0.1);
	}

	.tuner-terminate-btn {
		font-size: 0.72rem;
		padding: 0.15rem 0.4rem;
		border-radius: 0.25rem;
		background: rgba(224, 90, 90, 0.15);
		color: #e05a5a;
		border: 1px solid rgba(224, 90, 90, 0.3);
		cursor: pointer;
		transition:
			background 0.15s ease,
			color 0.15s ease;
	}

	.tuner-terminate-btn:hover {
		background: #e05a5a;
		color: #fff;
	}

	.tuner-status-empty {
		margin: 0;
		font-size: 0.8rem;
		color: var(--color-text-muted);
	}
</style>
