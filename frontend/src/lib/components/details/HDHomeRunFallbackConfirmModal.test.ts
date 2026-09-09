import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import HDHomeRunFallbackConfirmModal from './HDHomeRunFallbackConfirmModal.svelte';

describe('HDHomeRunFallbackConfirmModal.svelte', () => {
	it('renders fallback dialog with show title', () => {
		render(HDHomeRunFallbackConfirmModal, {
			props: {
				title: 'Late Night Talk',
				onConfirm: vi.fn(),
				onClose: vi.fn(),
			},
		});

		expect(screen.getByRole('alertdialog')).toBeInTheDocument();
		expect(screen.getByText(/Late Night Talk/i)).toBeInTheDocument();
	});

	it('calls onConfirm with dontAskAgain status', async () => {
		const onConfirm = vi.fn();
		render(HDHomeRunFallbackConfirmModal, {
			props: {
				title: 'Late Night Talk',
				onConfirm,
				onClose: vi.fn(),
			},
		});

		const checkbox = screen.getByRole('checkbox');
		expect(checkbox).not.toBeChecked();

		await fireEvent.click(checkbox);
		expect(checkbox).toBeChecked();

		const proceedBtn = screen.getByRole('button', { name: /Schedule on Built-in DVR/i });
		await fireEvent.click(proceedBtn);

		expect(onConfirm).toHaveBeenCalledWith(true);
	});

	it('calls onClose when cancel button is clicked', async () => {
		const onClose = vi.fn();
		render(HDHomeRunFallbackConfirmModal, {
			props: {
				title: 'Late Night Talk',
				onConfirm: vi.fn(),
				onClose,
			},
		});

		const cancelBtn = screen.getByRole('button', { name: /Cancel/i });
		await fireEvent.click(cancelBtn);

		expect(onClose).toHaveBeenCalled();
	});

	it('calls onClose on Escape key', async () => {
		const onClose = vi.fn();
		render(HDHomeRunFallbackConfirmModal, {
			props: {
				title: 'Late Night Talk',
				onConfirm: vi.fn(),
				onClose,
			},
		});

		await fireEvent.keyDown(window, { key: 'Escape' });
		expect(onClose).toHaveBeenCalled();
	});
});
