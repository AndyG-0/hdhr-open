import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import Tabs from './Tabs.svelte';

const TABS = [
	{ id: 'one', label: 'One' },
	{ id: 'two', label: 'Two' },
];

describe('Tabs', () => {
	it('renders all tabs', () => {
		render(Tabs, { tabs: TABS, activeId: 'one', onSelect: vi.fn() });

		expect(screen.getByRole('tab', { name: 'One' })).toBeInTheDocument();
		expect(screen.getByRole('tab', { name: 'Two' })).toBeInTheDocument();
	});

	it('marks the active tab via aria-selected', () => {
		render(Tabs, { tabs: TABS, activeId: 'two', onSelect: vi.fn() });

		expect(screen.getByRole('tab', { name: 'One' })).toHaveAttribute('aria-selected', 'false');
		expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute('aria-selected', 'true');
	});

	it('calls onSelect with the clicked tab id', async () => {
		const onSelect = vi.fn();
		render(Tabs, { tabs: TABS, activeId: 'one', onSelect });

		await fireEvent.click(screen.getByRole('tab', { name: 'Two' }));

		expect(onSelect).toHaveBeenCalledWith('two');
	});
});
