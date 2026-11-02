import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import RemoveDuplicatesModal from './RemoveDuplicatesModal.svelte';
import type { HDHomeRunRecording, HDHomeRunRecordingDuplicateGroup } from '$lib/api';

function rec(id: string, start: number): HDHomeRunRecording {
	return {
		recording_id: id,
		title: 'Jeopardy!',
		episode_title: 'Game 1',
		channel_name: 'WNBC',
		channel_number: '4.1',
		start,
		record_end: start + 1800,
		file_size_bytes: 1_000_000_000,
		provider: 'builtin',
	};
}

const groups: HDHomeRunRecordingDuplicateGroup[] = [
	{
		key: 'g1',
		title: 'Jeopardy!',
		episode_title: 'Game 1',
		category_type: 'shows',
		suggested_keep_id: 'keep',
		recordings: [rec('keep', 3_000_000), rec('dup1', 2_000_000), rec('dup2', 1_000_000)],
	},
];

function renderModal(overrides: Partial<{ groups: HDHomeRunRecordingDuplicateGroup[]; loading: boolean }> = {}) {
	const onConfirm = vi.fn();
	const onClose = vi.fn();
	render(RemoveDuplicatesModal, { groups, onConfirm, onClose, ...overrides });
	return { onConfirm, onClose };
}

function checkboxes(): HTMLInputElement[] {
	return screen.getAllByRole('checkbox') as HTMLInputElement[];
}

describe('RemoveDuplicatesModal', () => {
	it('starts with every copy checked except the suggested keeper', () => {
		renderModal();
		expect(checkboxes().map((c) => c.checked)).toEqual([false, true, true]);
		expect(screen.getByText('Suggested keep')).toBeTruthy();
		expect(screen.getByRole('button', { name: /Delete 2 recordings/ })).toBeTruthy();
	});

	it('updates the count when a copy is unchecked', async () => {
		renderModal();
		await fireEvent.click(checkboxes()[1]);
		expect(screen.getByRole('button', { name: /Delete 1 recording \(/ })).toBeTruthy();
	});

	it('warns when every copy is checked', async () => {
		renderModal();
		expect(screen.queryByRole('alert')).toBeNull();
		await fireEvent.click(checkboxes()[0]);
		expect(screen.getByRole('alert').textContent).toMatch(/Every copy/);
	});

	it('confirms with the checked ids', async () => {
		const { onConfirm } = renderModal();
		await fireEvent.click(checkboxes()[2]);
		await fireEvent.click(screen.getByRole('button', { name: /Delete 1 recording/ }));
		expect(onConfirm).toHaveBeenCalledWith(['dup1']);
	});

	it('disables delete when nothing is checked', async () => {
		renderModal();
		await fireEvent.click(checkboxes()[1]);
		await fireEvent.click(checkboxes()[2]);
		expect((screen.getByRole('button', { name: /Delete 0 recordings/ }) as HTMLButtonElement).disabled).toBe(true);
	});

	it('shows an empty state and closes on cancel', async () => {
		const { onClose } = renderModal({ groups: [] });
		expect(screen.getByText('No duplicate recordings found.')).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(onClose).toHaveBeenCalled();
	});
});
