import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import HDHomeRunKeywordRuleDialog from './HDHomeRunKeywordRuleDialog.svelte';
import type { HDHomeRunChannel } from '$lib/api';

describe('HDHomeRunKeywordRuleDialog.svelte', () => {
	const mockChannels: HDHomeRunChannel[] = [
		{
			channel_number: '4.1',
			name: 'KDFW',
			is_hd: true,
			is_drm: false,
			stream_url: 'http://tuner.local/stream/4.1',
			playback_url: null,
			now: null,
			next: null,
		},
		{
			channel_number: '5.1',
			name: 'KXAS',
			is_hd: true,
			is_drm: false,
			stream_url: 'http://tuner.local/stream/5.1',
			playback_url: null,
			now: null,
			next: null,
		},
	];

	it('renders dialog and disables submit when title is empty', () => {
		render(HDHomeRunKeywordRuleDialog, {
			props: {
				channels: mockChannels,
				loading: false,
				onConfirm: vi.fn(),
				onClose: vi.fn(),
			},
		});

		expect(screen.getByRole('dialog')).toBeInTheDocument();
		const submitBtn = screen.getByRole('button', { name: /Create Rule/i });
		expect(submitBtn).toBeDisabled();
	});

	it('enables submit and emits payload when form is filled and submitted', async () => {
		const onConfirm = vi.fn();
		render(HDHomeRunKeywordRuleDialog, {
			props: {
				channels: mockChannels,
				loading: false,
				onConfirm,
				onClose: vi.fn(),
			},
		});

		const titleInput = screen.getByPlaceholderText(/College Football/i);
		await fireEvent.input(titleInput, { target: { value: 'Football' } });

		const containsRadio = screen.getByRole('radio', { name: /Contains/i });
		await fireEvent.click(containsRadio);

		const keywordInput = screen.getByPlaceholderText(/Ohio State/i);
		await fireEvent.input(keywordInput, { target: { value: 'Cowboys' } });

		const submitBtn = screen.getByRole('button', { name: /Create Rule/i });
		expect(submitBtn).toBeEnabled();

		await fireEvent.click(submitBtn);

		expect(onConfirm).toHaveBeenCalledWith({
			title: 'Football',
			titleMatchMode: 'contains',
			keywordQuery: 'Cowboys',
			channel: undefined,
			startPadding: undefined,
			endPadding: undefined,
			recentOnly: false,
			maxEpisodesToKeep: undefined,
		});
	});

	it('supports selecting custom channels', async () => {
		const onConfirm = vi.fn();
		render(HDHomeRunKeywordRuleDialog, {
			props: {
				channels: mockChannels,
				loading: false,
				onConfirm,
				onClose: vi.fn(),
			},
		});

		const titleInput = screen.getByPlaceholderText(/College Football/i);
		await fireEvent.input(titleInput, { target: { value: 'News' } });

		const customChannelsRadio = screen.getByRole('radio', { name: /Specific channels/i });
		await fireEvent.click(customChannelsRadio);

		const ch41Checkbox = screen.getByRole('checkbox', { name: /4\.1/i });
		await fireEvent.click(ch41Checkbox);

		const submitBtn = screen.getByRole('button', { name: /Create Rule/i });
		await fireEvent.click(submitBtn);

		expect(onConfirm).toHaveBeenCalledWith(
			expect.objectContaining({
				title: 'News',
				channel: '4.1',
			}),
		);
	});

	it('calls onClose when close button is clicked', async () => {
		const onClose = vi.fn();
		render(HDHomeRunKeywordRuleDialog, {
			props: {
				loading: false,
				onConfirm: vi.fn(),
				onClose,
			},
		});

		const closeBtn = screen.getByRole('button', { name: 'Cancel' });
		await fireEvent.click(closeBtn);

		expect(onClose).toHaveBeenCalled();
	});
});
