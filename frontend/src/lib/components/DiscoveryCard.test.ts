import { render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';
import DiscoveryCard from './DiscoveryCard.svelte';
import type { HDHomeRunGuideEntry } from '$lib/api';

function makeAiring(overrides: Partial<HDHomeRunGuideEntry> = {}): HDHomeRunGuideEntry {
	return {
		title: 'Morning Show',
		episode_title: null,
		start: null,
		end: null,
		channel_number: '4.1',
		...overrides,
	};
}

describe('DiscoveryCard', () => {
	it('shows a source badge for a non-personalized item', () => {
		render(DiscoveryCard, { airing: makeAiring({ source: 'network_pick' }), onSelect: vi.fn() });

		expect(screen.getByText('Network pick')).toBeInTheDocument();
	});

	it('hides the source badge for a personalized item', () => {
		render(DiscoveryCard, { airing: makeAiring({ source: 'personalized' }), onSelect: vi.fn() });

		expect(screen.queryByText('Network pick')).not.toBeInTheDocument();
		expect(screen.queryByText('Active rule')).not.toBeInTheDocument();
	});

	it('hides the source badge when source is absent', () => {
		render(DiscoveryCard, { airing: makeAiring(), onSelect: vi.fn() });

		expect(screen.queryByText('Favorite team')).not.toBeInTheDocument();
	});
});
