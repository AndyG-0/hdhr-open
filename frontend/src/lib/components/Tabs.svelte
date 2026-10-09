<script lang="ts">
	interface Tab {
		id: string;
		label: string;
	}

	interface Props {
		tabs: Tab[];
		activeId: string;
		onSelect: (id: string) => void;
	}

	let { tabs, activeId, onSelect }: Props = $props();
</script>

<div class="tabs" role="tablist">
	{#each tabs as tab (tab.id)}
		<button
			type="button"
			role="tab"
			id={`tab-${tab.id}`}
			aria-selected={activeId === tab.id}
			aria-controls={`panel-${tab.id}`}
			class="tab"
			class:active={activeId === tab.id}
			onclick={() => onSelect(tab.id)}
		>
			{tab.label}
		</button>
	{/each}
</div>

<style>
	.tabs {
		display: flex;
		gap: 0.25rem;
		border-bottom: 1px solid var(--color-border);
		margin-bottom: 1.5rem;
		overflow-x: auto;
	}

	.tab {
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		padding: 0.6rem 1rem;
		font: inherit;
		color: var(--color-text-muted);
		cursor: pointer;
		white-space: nowrap;
	}

	.tab:hover {
		background: var(--color-surface-hover);
		color: var(--color-text);
	}

	.tab.active {
		color: var(--color-accent);
		border-bottom-color: var(--color-accent);
	}
</style>
