import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import HDHomeRunCancelRuleModal from './HDHomeRunCancelRuleModal.svelte';

describe('HDHomeRunCancelRuleModal.svelte', () => {
	it('renders confirmation dialog with title', () => {
		render(HDHomeRunCancelRuleModal, {
			props: {
				title: 'Doctor Who',
				onConfirm: vi.fn(),
				onClose: vi.fn(),
			},
		});

		expect(screen.getByRole('alertdialog')).toBeInTheDocument();
		expect(screen.getByText(/Doctor Who/i)).toBeInTheDocument();
	});

	it('calls onConfirm when clicking confirm button', async () => {
		const onConfirm = vi.fn();
		render(HDHomeRunCancelRuleModal, {
			props: {
				title: 'Doctor Who',
				onConfirm,
				onClose: vi.fn(),
			},
		});

		const confirmBtn = screen.getByRole('button', { name: /Cancel Recording/i });
		await fireEvent.click(confirmBtn);

		expect(onConfirm).toHaveBeenCalled();
	});

	it('calls onClose when clicking keep recording button', async () => {
		const onClose = vi.fn();
		render(HDHomeRunCancelRuleModal, {
			props: {
				title: 'Doctor Who',
				onConfirm: vi.fn(),
				onClose,
			},
		});

		const keepBtn = screen.getByRole('button', { name: /Keep Recording/i });
		await fireEvent.click(keepBtn);

		expect(onClose).toHaveBeenCalled();
	});

	it('calls onClose when Escape key is pressed', async () => {
		const onClose = vi.fn();
		render(HDHomeRunCancelRuleModal, {
			props: {
				title: 'Doctor Who',
				onConfirm: vi.fn(),
				onClose,
			},
		});

		await fireEvent.keyDown(window, { key: 'Escape' });
		expect(onClose).toHaveBeenCalled();
	});
});
