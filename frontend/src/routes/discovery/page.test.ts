import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const { getDiscovery, getHDHomeRunChannels, getDvrInfo } = vi.hoisted(() => ({
	getDiscovery: vi.fn(),
	getHDHomeRunChannels: vi.fn(),
	getDvrInfo: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: {
		getDiscovery,
		getHDHomeRunChannels,
		getDvrInfo,
	},
}));

import Page from './+page.svelte';

describe('discovery +page.svelte', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getHDHomeRunChannels.mockResolvedValue({ channels: [], guide_available: true });
		getDvrInfo.mockResolvedValue({ is_builtin: true });
	});

	it('shows the empty-state hint when there are no recommendations', async () => {
		getDiscovery.mockResolvedValue({ enabled: true, has_profile: false, items: [] });

		render(Page);

		expect(
			await screen.findByText('No recommendations right now. Check back after the guide updates.'),
		).toBeInTheDocument();
	});

	it('filters the grid to the selected bucket without issuing a second fetch', async () => {
		getDiscovery.mockResolvedValue({
			enabled: true,
			has_profile: true,
			items: [
				{
					title: 'Personalized Drama',
					bucket: 'shows',
					source: 'personalized',
					channel_number: '4.1',
					start: null,
					end: null,
					episode_title: null,
				},
				{
					title: 'Oscar Marathon',
					bucket: 'movies',
					source: 'network_pick',
					channel_number: '5.1',
					start: null,
					end: null,
					episode_title: null,
				},
				{
					title: 'Lakers at Celtics',
					bucket: 'sports',
					source: 'favorite_team',
					channel_number: '6.1',
					start: null,
					end: null,
					episode_title: null,
				},
			],
		});

		render(Page);

		expect(await screen.findByText('Personalized Drama')).toBeInTheDocument();
		expect(screen.getByText('Oscar Marathon')).toBeInTheDocument();
		expect(screen.getByText('Lakers at Celtics')).toBeInTheDocument();

		await fireEvent.click(screen.getByRole('button', { name: /Sports/ }));

		expect(screen.getByText('Lakers at Celtics')).toBeInTheDocument();
		expect(screen.queryByText('Personalized Drama')).not.toBeInTheDocument();
		expect(screen.queryByText('Oscar Marathon')).not.toBeInTheDocument();
		expect(getDiscovery).toHaveBeenCalledTimes(1);

		await fireEvent.click(screen.getByRole('button', { name: /All/ }));

		expect(screen.getByText('Personalized Drama')).toBeInTheDocument();
		expect(screen.getByText('Oscar Marathon')).toBeInTheDocument();
		expect(screen.getByText('Lakers at Celtics')).toBeInTheDocument();
		expect(getDiscovery).toHaveBeenCalledTimes(1);
	});

	it('groups items under category headings in the all view, and hides headings for a single-bucket filter', async () => {
		getDiscovery.mockResolvedValue({
			enabled: true,
			has_profile: true,
			items: [
				{
					title: 'Personalized Drama',
					bucket: 'shows',
					source: 'personalized',
					channel_number: '4.1',
					start: null,
					end: null,
					episode_title: null,
				},
				{
					title: 'Oscar Marathon',
					bucket: 'movies',
					source: 'network_pick',
					channel_number: '5.1',
					start: null,
					end: null,
					episode_title: null,
				},
				{
					title: 'Lakers at Celtics',
					bucket: 'sports',
					source: 'favorite_team',
					channel_number: '6.1',
					start: null,
					end: null,
					episode_title: null,
				},
			],
		});

		const { container } = render(Page);

		await screen.findByText('Personalized Drama');
		const headingTexts = () =>
			Array.from(container.querySelectorAll('h3.category-heading')).map((el) => el.textContent);
		expect(headingTexts()).toEqual(['📺 Shows (1)', '🎬 Movies (1)', '🏆 Sports (1)']);

		await fireEvent.click(screen.getByRole('button', { name: /Sports/ }));

		expect(headingTexts()).toEqual([]);
		expect(screen.getByText('Lakers at Celtics')).toBeInTheDocument();
	});

	it('preserves recommended order within a category section', async () => {
		getDiscovery.mockResolvedValue({
			enabled: true,
			has_profile: true,
			items: [
				{
					title: 'Top Pick Show',
					bucket: 'shows',
					source: 'personalized',
					channel_number: '4.1',
					start: null,
					end: null,
					episode_title: null,
				},
				{
					title: 'Second Pick Show',
					bucket: 'shows',
					source: 'network_pick',
					channel_number: '4.2',
					start: null,
					end: null,
					episode_title: null,
				},
			],
		});

		render(Page);

		await screen.findByText('Top Pick Show');
		const titles = screen.getAllByText(/Pick Show$/).map((el) => el.textContent);
		expect(titles).toEqual(['Top Pick Show', 'Second Pick Show']);
	});

	it('shows the why-recommended badge only for non-personalized items', async () => {
		getDiscovery.mockResolvedValue({
			enabled: true,
			has_profile: true,
			items: [
				{
					title: 'Personalized Drama',
					bucket: 'shows',
					source: 'personalized',
					channel_number: '4.1',
					start: null,
					end: null,
					episode_title: null,
				},
				{
					title: 'Oscar Marathon',
					bucket: 'movies',
					source: 'network_pick',
					channel_number: '5.1',
					start: null,
					end: null,
					episode_title: null,
				},
			],
		});

		render(Page);

		expect(await screen.findByText('Network pick')).toBeInTheDocument();
	});
});
