import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import PriorityList from './PriorityList.svelte';

function renderList(overrides: Partial<Record<string, unknown>> = {}) {
	const onReorder = vi.fn();
	const onSave = vi.fn();
	render(PriorityList, {
		heading: 'Priority Heading',
		hint: 'Priority hint text',
		items: ['a', 'b', 'c'],
		onReorder,
		itemLabel: (item: string) => `Label ${item}`,
		itemSubLabel: (item: string) => `Sub ${item}`,
		moveUpLabel: 'Move Up',
		moveDownLabel: 'Move Down',
		saving: false,
		saved: false,
		error: null,
		savedLabel: 'Saved!',
		saveLabel: 'Save',
		savingLabel: 'Saving...',
		onSave,
		...overrides,
	});
	return { onReorder, onSave };
}

describe('PriorityList', () => {
	it('renders items in order with labels', () => {
		renderList();
		expect(screen.getByText('Priority Heading')).toBeInTheDocument();
		expect(screen.getByText('Label a')).toBeInTheDocument();
		expect(screen.getByText('Sub b')).toBeInTheDocument();
	});

	it('swaps two items when moving down, keeping the rest in place', async () => {
		const { onReorder } = renderList();
		const downButtons = screen.getAllByRole('button', { name: 'Move Down' });
		await fireEvent.click(downButtons[0]);
		expect(onReorder).toHaveBeenCalledWith(['b', 'a', 'c']);
	});

	it('swaps two items when moving up', async () => {
		const { onReorder } = renderList();
		const upButtons = screen.getAllByRole('button', { name: 'Move Up' });
		await fireEvent.click(upButtons[1]);
		expect(onReorder).toHaveBeenCalledWith(['b', 'a', 'c']);
	});

	it('disables the first move-up and last move-down buttons', () => {
		renderList();
		const upButtons = screen.getAllByRole('button', { name: 'Move Up' });
		const downButtons = screen.getAllByRole('button', { name: 'Move Down' });
		expect(upButtons[0]).toBeDisabled();
		expect(downButtons[downButtons.length - 1]).toBeDisabled();
	});

	it('calls onSave when the save button is clicked', async () => {
		const { onSave } = renderList();
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		expect(onSave).toHaveBeenCalled();
	});

	it('shows the saving label and disables controls while saving', () => {
		renderList({ saving: true });
		expect(screen.getByRole('button', { name: 'Saving...' })).toBeDisabled();
		for (const button of screen.getAllByRole('button', { name: /Move (Up|Down)/ })) {
			expect(button).toBeDisabled();
		}
	});

	it('shows the saved label when saved is true', () => {
		renderList({ saved: true });
		expect(screen.getByText('Saved!')).toBeInTheDocument();
	});

	it('shows the error message when error is set', () => {
		renderList({ error: 'Something broke' });
		expect(screen.getByText('Something broke')).toBeInTheDocument();
	});

	it('renders inside a <section> element', () => {
		renderList();
		expect(screen.getByText('Priority Heading').closest('section')).toBeInTheDocument();
	});
});
