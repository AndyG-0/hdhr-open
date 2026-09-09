import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('$env/dynamic/public', () => ({
	env: { PUBLIC_API_BASE_URL: 'http://api.test' },
}));

const {
	watchCastState,
	requestCastSession,
	loadCastMedia,
	endCastSession,
	getActiveCastSessionId,
	setActiveCastSessionId,
} = vi.hoisted(() => ({
	watchCastState: vi.fn(),
	requestCastSession: vi.fn(),
	loadCastMedia: vi.fn(),
	endCastSession: vi.fn(),
	getActiveCastSessionId: vi.fn(),
	setActiveCastSessionId: vi.fn(),
}));

vi.mock('$lib/cast/cast-loader', () => ({
	watchCastState,
	requestCastSession,
	loadCastMedia,
	endCastSession,
	getActiveCastSessionId,
	setActiveCastSessionId,
}));

vi.mock('$lib/api', () => ({
	api: {
		stopHlsSession: vi.fn(),
	},
}));

import CastButton from './CastButton.svelte';

describe('CastButton.svelte', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('does not render button if no devices are available', () => {
		watchCastState.mockImplementation((cb) => {
			cb('no_devices_available');
			return () => {};
		});

		render(CastButton, {
			props: {
				title: 'Test Stream',
				buildContentUrl: vi.fn(),
			},
		});

		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});

	it('renders cast button when devices are available and initiates cast session on click', async () => {
		watchCastState.mockImplementation((cb) => {
			cb('not_connected');
			return () => {};
		});

		const mockSession = { id: 'session-123' };
		requestCastSession.mockResolvedValue(mockSession);
		loadCastMedia.mockResolvedValue(undefined);

		const buildContentUrl = vi.fn().mockResolvedValue({
			url: 'http://stream.m3u8',
			sessionId: 'cast-hls-1',
		});
		const onCastingChange = vi.fn();

		render(CastButton, {
			props: {
				title: 'Evening Show',
				subtitle: 'Episode 1',
				buildContentUrl,
				onCastingChange,
			},
		});

		const castBtn = screen.getByRole('button', { name: /^Cast$/i });
		expect(castBtn).toBeInTheDocument();

		await fireEvent.click(castBtn);

		await vi.waitFor(() => {
			expect(requestCastSession).toHaveBeenCalled();
			expect(buildContentUrl).toHaveBeenCalled();
			expect(setActiveCastSessionId).toHaveBeenCalledWith('cast-hls-1');
			expect(loadCastMedia).toHaveBeenCalledWith(mockSession, {
				contentUrl: 'http://stream.m3u8',
				contentType: 'application/x-mpegurl',
				title: 'Evening Show',
				subtitle: 'Episode 1',
				imageUrl: undefined,
			});
			expect(onCastingChange).toHaveBeenCalledWith(true);
		});
	});

	it('ends cast session when clicked while already casting', async () => {
		watchCastState.mockImplementation((cb) => {
			cb('connected');
			return () => {};
		});

		render(CastButton, {
			props: {
				title: 'Evening Show',
				buildContentUrl: vi.fn(),
			},
		});

		const stopBtn = screen.getByRole('button', { name: /Stop Casting/i });
		await fireEvent.click(stopBtn);

		expect(endCastSession).toHaveBeenCalled();
	});
});
