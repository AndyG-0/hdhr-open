import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';

const { heartbeatWatch, stopWatch } = vi.hoisted(() => ({
	heartbeatWatch: vi.fn().mockResolvedValue(undefined),
	stopWatch: vi.fn(),
}));

vi.mock('$lib/api', () => ({
	api: { heartbeatWatch, stopWatch },
}));

const { getActiveCastSessionId, endCastSession, setActiveCastSessionId } = vi.hoisted(() => ({
	getActiveCastSessionId: vi.fn<() => string | null>(() => null),
	endCastSession: vi.fn(),
	setActiveCastSessionId: vi.fn(),
}));

vi.mock('$lib/cast/cast-loader', () => ({
	getActiveCastSessionId,
	endCastSession,
	setActiveCastSessionId,
}));

import { playback, startPlayback, stopPlayback, updateContext, type PlaybackMedia } from './playback';

const media = (overrides: Partial<PlaybackMedia> = {}): PlaybackMedia => ({
	title: 'Channel 4.1',
	url: 'https://example.com/stream',
	seekable: false,
	...overrides,
});

const context = () => ({
	channels: [],
	favoriteChannels: new Set<string>(),
	recordingRules: [],
	pendingRuleIds: new Set<string>(),
	officialDvrActive: false,
	recordingLoading: null,
});

describe('playback store', () => {
	beforeEach(() => {
		// Flush any dangling session left by the previous test before clearing
		// mocks, so that cleanup call doesn't get recorded as this test's own.
		stopPlayback();
		vi.clearAllMocks();
		getActiveCastSessionId.mockReturnValue(null);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('starts playback, publishing media/originPath/context', () => {
		startPlayback(media({ title: 'KDFW' }), '/', context());

		const state = get(playback);
		expect(state.media?.title).toBe('KDFW');
		expect(state.originPath).toBe('/');
		expect(state.context).not.toBeNull();
	});

	it('stops the previous watch session before starting a new one (channel zap)', () => {
		startPlayback(media({ isWatchSession: true, watchSessionId: 'sess1' }), '/', context());
		expect(stopWatch).not.toHaveBeenCalled();

		startPlayback(media({ isWatchSession: true, watchSessionId: 'sess2' }), '/', context());
		expect(stopWatch).toHaveBeenCalledWith('sess1');
		expect(stopWatch).not.toHaveBeenCalledWith('sess2');
	});

	it('does not call stopWatch for non-watch-session media', () => {
		startPlayback(media(), '/', context());
		stopPlayback();
		expect(stopWatch).not.toHaveBeenCalled();
	});

	it('heartbeats a watch session on an interval and stops on stopPlayback', () => {
		vi.useFakeTimers();
		startPlayback(media({ isWatchSession: true, watchSessionId: 'sess1' }), '/', context());

		vi.advanceTimersByTime(20_000);
		expect(heartbeatWatch).toHaveBeenCalledWith('sess1');
		expect(heartbeatWatch).toHaveBeenCalledTimes(1);

		stopPlayback();
		vi.advanceTimersByTime(60_000);
		expect(heartbeatWatch).toHaveBeenCalledTimes(1);
	});

	it('merges partial updates into context without touching media/originPath', () => {
		startPlayback(media({ title: 'KDFW' }), '/', context());

		updateContext({ recordingLoading: 'rule-1' });

		const state = get(playback);
		expect(state.media?.title).toBe('KDFW');
		expect(state.originPath).toBe('/');
		expect(state.context?.recordingLoading).toBe('rule-1');
	});

	it('ignores updateContext when nothing is playing', () => {
		updateContext({ recordingLoading: 'rule-1' });
		expect(get(playback).context).toBeNull();
	});

	it('clears media/originPath/context on stopPlayback', () => {
		startPlayback(media(), '/', context());
		stopPlayback();

		const state = get(playback);
		expect(state.media).toBeNull();
		expect(state.originPath).toBeNull();
		expect(state.context).toBeNull();
	});

	it('explicitly ends an active Cast session on stopPlayback', () => {
		// Models cast-loader's real contract: setActiveCastSessionId(null)
		// (called right after endCastSession()) is what getActiveCastSessionId
		// reflects afterward, so a second teardown doesn't re-fire.
		let sessionId: string | null = 'cast-session-1';
		getActiveCastSessionId.mockImplementation(() => sessionId);
		setActiveCastSessionId.mockImplementation((id: string | null) => {
			sessionId = id;
		});

		startPlayback(media(), '/', context());
		stopPlayback();

		expect(endCastSession).toHaveBeenCalledTimes(1);
		expect(setActiveCastSessionId).toHaveBeenCalledWith(null);
	});

	it('does not touch Cast session teardown when nothing is casting', () => {
		getActiveCastSessionId.mockReturnValue(null);
		startPlayback(media(), '/', context());

		stopPlayback();

		expect(endCastSession).not.toHaveBeenCalled();
		expect(setActiveCastSessionId).not.toHaveBeenCalled();
	});
});
