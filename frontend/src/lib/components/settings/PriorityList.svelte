<script lang="ts" generics="T extends string">
	interface Props {
		heading: string;
		hint: string;
		items: T[];
		onReorder: (next: T[]) => void;
		itemLabel: (item: T) => string;
		itemSubLabel: (item: T) => string;
		moveUpLabel: string;
		moveDownLabel: string;
		saving: boolean;
		saved: boolean;
		error: string | null;
		savedLabel: string;
		saveLabel: string;
		savingLabel: string;
		onSave: () => void;
	}

	let {
		heading,
		hint,
		items,
		onReorder,
		itemLabel,
		itemSubLabel,
		moveUpLabel,
		moveDownLabel,
		saving,
		saved,
		error,
		savedLabel,
		saveLabel,
		savingLabel,
		onSave,
	}: Props = $props();

	function moveUp(index: number) {
		if (index <= 0) return;
		const next = [...items];
		const temp = next[index - 1];
		next[index - 1] = next[index];
		next[index] = temp;
		onReorder(next);
	}

	function moveDown(index: number) {
		if (index >= items.length - 1) return;
		const next = [...items];
		const temp = next[index + 1];
		next[index + 1] = next[index];
		next[index] = temp;
		onReorder(next);
	}
</script>

<section>
	<div class="section-header-row">
		<div>
			<h3>{heading}</h3>
			<p class="hint">{hint}</p>
		</div>
	</div>

	<div class="priority-list">
		{#each items as item, index (item)}
			<div class="priority-item">
				<div class="priority-info">
					<span class="priority-badge">{index + 1}</span>
					<div class="priority-text">
						<span class="priority-name">{itemLabel(item)}</span>
						<span class="priority-sub">{itemSubLabel(item)}</span>
					</div>
				</div>
				<div class="priority-actions">
					<button
						type="button"
						class="clear small"
						disabled={index === 0 || saving}
						onclick={() => moveUp(index)}
						aria-label={moveUpLabel}
					>
						▲
					</button>
					<button
						type="button"
						class="clear small"
						disabled={index === items.length - 1 || saving}
						onclick={() => moveDown(index)}
						aria-label={moveDownLabel}
					>
						▼
					</button>
				</div>
			</div>
		{/each}
	</div>

	{#if error}
		<p class="hint error">{error}</p>
	{/if}
	{#if saved}
		<p class="hint ok">{savedLabel}</p>
	{/if}

	<button type="button" class="save" disabled={saving} onclick={onSave}>
		{saving ? savingLabel : saveLabel}
	</button>
</section>

<style>
	.priority-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		margin: 0.5rem 0;
	}

	.priority-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.5rem 0.75rem;
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: 0.5rem;
		gap: 1rem;
	}

	.priority-info {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.priority-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		background: var(--color-accent);
		color: var(--color-surface);
		font-weight: 700;
		font-size: 0.8rem;
		flex-shrink: 0;
	}

	.priority-text {
		display: flex;
		flex-direction: column;
	}

	.priority-name {
		font-weight: 600;
		font-size: 0.9rem;
	}

	.priority-sub {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.priority-actions {
		display: flex;
		gap: 0.25rem;
	}
</style>
