import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

vi.mock('$env/dynamic/public', () => ({ env: { PUBLIC_API_BASE_URL: 'http://api.test' } }));

import { createAirPlayController, isAirPlaySupported } from './airplay-controller';

describe('airplay-controller', () => {
	let mockVideo: HTMLVideoElement & {
		webkitShowPlaybackTargetPicker: () => void;
		currentTime: number;
		src: string;
		load: () => void;
		play: () => Promise<void>;
		attributes: Record<string, string>;
	};

	beforeEach(() => {
		// Mock WebKitPlaybackTargetAvailabilityEvent in globalThis
		(globalThis as unknown as Record<string, unknown>).WebKitPlaybackTargetAvailabilityEvent = class {};

		const attributes: Record<string, string> = { crossorigin: 'use-credentials' };
		mockVideo = {
			webkitShowPlaybackTargetPicker: vi.fn(),
			currentTime: 15,
			src: 'blob:http://localhost/mse-blob',
			load: vi.fn(),
			play: vi.fn().mockResolvedValue(undefined),
			attributes,
			getAttribute: vi.fn((name: string) => attributes[name] ?? null),
			setAttribute: vi.fn((name: string, val: string) => {
				attributes[name] = val;
			}),
			removeAttribute: vi.fn((name: string) => {
				delete attributes[name];
			}),
			addEventListener: vi.fn(),
			removeEventListener: vi.fn(),
		} as unknown as typeof mockVideo;
	});

	afterEach(() => {
		delete (globalThis as unknown as Record<string, unknown>).WebKitPlaybackTargetAvailabilityEvent;
		vi.restoreAllMocks();
	});

	function makeOptions(overrides: Record<string, unknown> = {}) {
		let baseOffset = 100;
		let videoTime = 10;
		return {
			getVideoElement: () => mockVideo,
			getDestroyed: () => false,
			getSeekable: () => true,
			getBaseOffsetSeconds: () => baseOffset,
			setBaseOffsetSeconds: vi.fn((v: number) => {
				baseOffset = v;
			}),
			getVideoCurrentTime: () => videoTime,
			setVideoCurrentTime: vi.fn((v: number) => {
				videoTime = v;
			}),
			getCurrentAudioIndex: () => 1,
			getSrc: () => 'http://api.test/live.ts',
			buildStreamUrl: vi.fn((resumeAt: number, audioIndex?: number | null) => `http://api.test/stream?start=${resumeAt}&audio=${audioIndex}`),
			buildCastContentUrl: vi.fn().mockResolvedValue({ url: 'http://api.test/hls/cast.m3u8', sessionId: 'hls-sess-1' }),
			onAvailabilityChange: vi.fn(),
			teardownMpegtsPlayer: vi.fn(),
			createMpegtsPlayerAt: vi.fn(),
			safePlay: vi.fn(),
			stopHlsSession: vi.fn(),
			refreshCaptions: vi.fn(),
			...overrides,
		};
	}

	it('detects AirPlay support correctly', () => {
		expect(isAirPlaySupported()).toBe(true);
	});

	it('showAirPlayPicker invokes webkitShowPlaybackTargetPicker synchronously', () => {
		const options = makeOptions();
		const controller = createAirPlayController(options);

		controller.showAirPlayPicker();
		expect(mockVideo.webkitShowPlaybackTargetPicker).toHaveBeenCalledTimes(1);
	});

	it('swaps video element to HLS for_cast URL and drops crossorigin when route is available', async () => {
		const options = makeOptions();
		const controller = createAirPlayController(options);

		let listener: ((event: Event) => void) | undefined;
		mockVideo.addEventListener = vi.fn((event: string, handler: unknown) => {
			if (event === 'webkitplaybacktargetavailabilitychanged') {
				listener = handler as (e: Event) => void;
			}
		});

		const detach = controller.attachVideoElement(mockVideo);
		expect(mockVideo.addEventListener).toHaveBeenCalledWith(
			'webkitplaybacktargetavailabilitychanged',
			expect.any(Function),
		);

		// Trigger availability = 'available'
		listener?.({ availability: 'available' } as unknown as Event);
		await vi.waitFor(() => expect(controller.getAirPlaySessionId()).toBe('hls-sess-1'));

		expect(options.onAvailabilityChange).toHaveBeenCalledWith(true);
		expect(options.teardownMpegtsPlayer).toHaveBeenCalledTimes(1);
		expect(mockVideo.removeAttribute).toHaveBeenCalledWith('crossorigin');
		expect(mockVideo.src).toBe('http://api.test/hls/cast.m3u8');
		expect(mockVideo.load).toHaveBeenCalledTimes(1);
		expect(options.safePlay).toHaveBeenCalledTimes(1);

		detach();
		expect(mockVideo.removeEventListener).toHaveBeenCalledWith(
			'webkitplaybacktargetavailabilitychanged',
			listener,
		);
	});

	it('restores crossorigin and restarts MSE player at resumed offset when route disconnects', async () => {
		const options = makeOptions();
		const controller = createAirPlayController(options);

		let listener: ((event: Event) => void) | undefined;
		mockVideo.addEventListener = vi.fn((event: string, handler: unknown) => {
			if (event === 'webkitplaybacktargetavailabilitychanged') {
				listener = handler as (e: Event) => void;
			}
		});

		controller.attachVideoElement(mockVideo);

		// Connect
		listener?.({ availability: 'available' } as unknown as Event);
		await vi.waitFor(() => expect(controller.getAirPlaySessionId()).toBe('hls-sess-1'));

		// While on AirPlay, currentTime advanced by 20s
		mockVideo.currentTime = 20;

		// Disconnect
		listener?.({ availability: 'not-available' } as unknown as Event);

		expect(options.stopHlsSession).toHaveBeenCalledWith('hls-sess-1');
		expect(controller.getAirPlaySessionId()).toBeNull();
		expect(mockVideo.setAttribute).toHaveBeenCalledWith('crossorigin', 'use-credentials');
		expect(mockVideo.removeAttribute).toHaveBeenCalledWith('src');
		expect(mockVideo.load).toHaveBeenCalled();

		// airplayResumeFrom was seekable (100 + 10 = 110) + 20 = 130
		expect(options.setBaseOffsetSeconds).toHaveBeenCalledWith(130);
		expect(options.setVideoCurrentTime).toHaveBeenCalledWith(0);
		expect(options.refreshCaptions).toHaveBeenCalledTimes(1);
		expect(options.createMpegtsPlayerAt).toHaveBeenCalledWith(
			mockVideo,
			'http://api.test/stream?start=130&audio=1',
		);
	});

	it('cleans up active HLS session on destroy()', async () => {
		const options = makeOptions();
		const controller = createAirPlayController(options);

		let listener: ((event: Event) => void) | undefined;
		mockVideo.addEventListener = vi.fn((event: string, handler: unknown) => {
			if (event === 'webkitplaybacktargetavailabilitychanged') {
				listener = handler as (e: Event) => void;
			}
		});

		controller.attachVideoElement(mockVideo);
		listener?.({ availability: 'available' } as unknown as Event);
		await vi.waitFor(() => expect(controller.getAirPlaySessionId()).toBe('hls-sess-1'));

		controller.destroy();
		expect(options.stopHlsSession).toHaveBeenCalledWith('hls-sess-1');
		expect(controller.getAirPlaySessionId()).toBeNull();
	});
});
