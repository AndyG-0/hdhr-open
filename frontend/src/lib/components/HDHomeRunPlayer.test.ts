import { render, screen, fireEvent } from '@testing-library/svelte';
import { describe, expect, it, vi, beforeEach } from 'vitest';

// mpegts.js drives an MSE pipeline that jsdom has no implementation for, so
// the player itself is stubbed down to the one thing this component's error
// handling depends on: the ERROR event and its type argument.
const { createPlayer, listeners } = vi.hoisted(() => {
	const listeners = new Map<string, (...args: unknown[]) => void>();
	return {
		listeners,
		createPlayer: vi.fn(() => ({
			on: (event: string, handler: (...args: unknown[]) => void) => listeners.set(event, handler),
			attachMediaElement: vi.fn(),
			load: vi.fn(),
			play: vi.fn(),
			pause: vi.fn(),
			unload: vi.fn(),
			detachMediaElement: vi.fn(),
			destroy: vi.fn(),
		})),
	};
});
vi.mock('mpegts.js', () => ({
	default: {
		createPlayer,
		Events: { ERROR: 'error' },
		ErrorTypes: { NETWORK_ERROR: 'NetworkError', MEDIA_ERROR: 'MediaError' },
	},
}));

const {
	hdhomerunRecordingStreamUrl,
	hdhomerunRecordingDetail,
	hdhomerunRecordingCaptionsUrl,
	hdhomerunRecordingThumbnailVttUrl,
	hdhomerunRecordingThumbnailSpriteUrl,
	addHDHomeRunRecordingRule,
	deleteHDHomeRunRecordingRule,
} = vi.hoisted(() => ({
	hdhomerunRecordingStreamUrl: vi.fn(
		(playUrl: string, options?: { start?: number; audioIndex?: number; recordingId?: string | null }) =>
			`https://example.com/recording-stream?url=${playUrl}&start=${options?.start ?? ''}&audio=${options?.audioIndex ?? ''}`,
	),
	hdhomerunRecordingDetail: vi.fn(),
	hdhomerunRecordingCaptionsUrl: vi.fn(
		(opts: { recordingId: string }) => `https://example.com/captions/${opts.recordingId}.vtt`,
	),
	hdhomerunRecordingThumbnailVttUrl: vi.fn(
		(opts: { recordingId: string }) => `https://example.com/thumbs/${opts.recordingId}.vtt`,
	),
	hdhomerunRecordingThumbnailSpriteUrl: vi.fn(
		(opts: { recordingId: string }) => `https://example.com/thumbs/${opts.recordingId}.jpg`,
	),
	addHDHomeRunRecordingRule: vi.fn(),
	deleteHDHomeRunRecordingRule: vi.fn(),
}));
vi.mock('$lib/api', () => ({
	api: {
		hdhomerunRecordingStreamUrl,
		hdhomerunRecordingDetail,
		hdhomerunRecordingCaptionsUrl,
		hdhomerunRecordingThumbnailVttUrl,
		hdhomerunRecordingThumbnailSpriteUrl,
		addHDHomeRunRecordingRule,
		deleteHDHomeRunRecordingRule,
	},
}));

// jsdom doesn't implement HTMLMediaElement.addTextTrack or VTTCue, so the
// component's caption-track management is faked out here the same way
// mpegts.js is above.
class FakeVTTCue {
	constructor(
		public startTime: number,
		public endTime: number,
		public text: string,
	) {}
}
(globalThis as unknown as { VTTCue: typeof FakeVTTCue }).VTTCue = FakeVTTCue;

function makeFakeTextTrack() {
	return {
		mode: 'hidden',
		cues: [] as FakeVTTCue[],
		addCue(cue: FakeVTTCue) {
			this.cues.push(cue);
		},
		removeCue(cue: FakeVTTCue) {
			this.cues = this.cues.filter((c) => c !== cue);
		},
	};
}
let fakeTextTrack = makeFakeTextTrack();
(HTMLMediaElement.prototype as unknown as { addTextTrack: () => typeof fakeTextTrack }).addTextTrack = () =>
	fakeTextTrack;

import HDHomeRunPlayer from './HDHomeRunPlayer.svelte';

const props = { src: 'https://example.com/stream/4.1', title: '4.1 KDFW', onClose: () => {} };

const seekableProps = {
	src: 'https://example.com/stream/4.1',
	title: 'Finished Show',
	onClose: () => {},
	playUrl: '/recorded/rec1',
	recordingId: 'rec1',
	startTimestamp: 1000,
	recordEndTimestamp: 2000,
	seekable: true,
};

async function raiseError(errorType: string) {
	// Let the component's dynamic import('mpegts.js') resolve and register.
	await vi.waitFor(() => expect(listeners.has('error')).toBe(true));
	listeners.get('error')!(errorType);
}

describe('HDHomeRunPlayer', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		listeners.clear();
		vi.unstubAllGlobals();
		fakeTextTrack = makeFakeTextTrack();
	});

	it("shows the backend's failure detail on a network error", async () => {
		// mpegts.js discards the response body, so the component re-requests
		// the stream to read the 502's detail — the only place the real
		// ffmpeg failure is reported.
		const fetchMock = vi.fn().mockResolvedValue({
			ok: false,
			json: async () => ({ detail: 'ffmpeg exited with code 1: No VA display found for device' }),
		});
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props });
		await raiseError('NetworkError');

		expect(await screen.findByText(/No VA display found for device/)).toBeInTheDocument();
		expect(fetchMock).toHaveBeenCalledWith(props.src, { credentials: 'include' });
	});

	it('falls back to the generic hint when the retry succeeds', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body: { cancel: vi.fn() } }));

		render(HDHomeRunPlayer, { props });
		await raiseError('NetworkError');

		expect(await screen.findByText(/Playback failed/)).toBeInTheDocument();
		expect(screen.queryByText(/ffmpeg/)).not.toBeInTheDocument();
	});

	it('does not re-request the stream for a non-network error', async () => {
		const fetchMock = vi.fn();
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props });
		await raiseError('MediaError');

		expect(await screen.findByText(/Playback failed/)).toBeInTheDocument();
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('builds the stream URL from the start of a completed seekable recording', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 120,
			video: null,
			audio: [],
			has_captions: false,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() =>
			expect(hdhomerunRecordingStreamUrl).toHaveBeenCalledWith('/recorded/rec1', {
				start: 0,
				audioIndex: undefined,
				recordingId: 'rec1',
			}),
		);
		expect(createPlayer).toHaveBeenCalledWith(
			expect.objectContaining({
				url: 'https://example.com/recording-stream?url=/recorded/rec1&start=0&audio=',
			}),
			expect.anything(),
		);
		expect(screen.getByRole('slider')).toBeInTheDocument();
	});

	it('parses the thumbnail VTT manifest and renders a hover preview at the scrubbed position', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 120,
			video: null,
			audio: [],
			has_captions: false,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vtt = ['WEBVTT', '', '00:00:10.000 --> 00:00:20.000', 'rec1.jpg#xywh=0,0,160,90', ''].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt }));
		vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
			left: 0,
			right: 200,
			top: 0,
			bottom: 20,
			width: 200,
			height: 20,
			x: 0,
			y: 0,
			toJSON: () => {},
		});

		render(HDHomeRunPlayer, { props: seekableProps });

		const scrubBar = await screen.findByRole('slider');
		await vi.waitFor(() => expect(hdhomerunRecordingThumbnailSpriteUrl).toHaveBeenCalled());
		await fireEvent.mouseMove(scrubBar, { clientX: 20 });

		expect(await screen.findByText('0:10')).toBeInTheDocument();
		expect(hdhomerunRecordingThumbnailSpriteUrl).toHaveBeenCalledWith({
			url: '/recorded/rec1',
			recordingId: 'rec1',
			recordEnd: 2000,
		});
	});

	it('re-times caption cues to the new playback origin after a seek', async () => {
		// The captions VTT is generated once for the whole recording, so its
		// cue at absolute 00:05:00 stays at absolute 00:05:00 regardless of
		// where playback starts - but each seek resets the video element's
		// own currentTime to 0, so the cue must be re-added shifted by
		// -baseOffsetSeconds every time the playback origin moves, or it
		// drifts out of sync with what's on screen.
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 1200,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vtt = ['WEBVTT', '', '00:05:00.000 --> 00:05:02.000', 'Hello there', ''].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt, json: async () => ({}) }));
		vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
			left: 0,
			right: 1200,
			top: 0,
			bottom: 20,
			width: 1200,
			height: 20,
			x: 0,
			y: 0,
			toJSON: () => {},
		});

		render(HDHomeRunPlayer, { props: seekableProps });
		const scrubBar = await screen.findByRole('slider');

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(300);
		expect(fakeTextTrack.cues[0].endTime).toBeCloseTo(302);

		// Seek to 100s - now before the cue's absolute start, so it should
		// re-appear shifted by -100s instead of staying at its original time.
		await fireEvent.click(scrubBar, { clientX: 100 });

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(200);
		expect(fakeTextTrack.cues[0].endTime).toBeCloseTo(202);
	});

	it('strips ffmpeg\'s literal "\\h" CEA-608 space escape from caption text', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 1200,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vtt = ['WEBVTT', '', '00:00:01.000 --> 00:00:02.000', '\\h\\h\\h\\h- Hello\\hthere', ''].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt, json: async () => ({}) }));

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		expect(fakeTextTrack.cues[0].text).toBe('    - Hello there');
	});

	it('parses MM:SS.mmm format and handles cue settings', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 1200,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vtt = [
			'WEBVTT',
			'',
			'00:05.000 --> 00:07.500 position:50% line:90% align:center',
			'Subtitles with settings',
			'',
		].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt, json: async () => ({}) }));

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(5);
		expect(fakeTextTrack.cues[0].endTime).toBeCloseTo(7.5);
		expect(fakeTextTrack.cues[0].text).toBe('Subtitles with settings');
	});

	it('toggles captions on/off via button and keyboard shortcut c', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 1200,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vtt = ['WEBVTT', '', '00:01.000 --> 00:03.000', 'Test', ''].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt, json: async () => ({}) }));

		render(HDHomeRunPlayer, { props: seekableProps });

		const ccButton = await screen.findByRole('button', { name: 'Subtitles / Closed Captions' });
		expect(ccButton.className).not.toMatch(/active/);

		// Click CC button to toggle on
		await fireEvent.click(ccButton);
		expect(ccButton.className).toMatch(/active/);
		// The native TextTrack must stay hidden - the .caption-overlay is the
		// only caption UI, since showing both double-renders every line.
		expect(fakeTextTrack.mode).toBe('hidden');

		// Press 'c' keyboard shortcut to toggle off
		await fireEvent.keyDown(window, { key: 'c' });
		expect(ccButton.className).not.toMatch(/active/);
		expect(fakeTextTrack.mode).toBe('hidden');
	});

	it('renders active caption text in the on-screen overlay when captions are enabled', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 1200,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vtt = [
			'WEBVTT',
			'',
			'00:00:00.000 --> 00:00:05.000',
			'<c.yellow>Welcome to the show</c>',
			'Enjoy the broadcast',
			'',
		].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt, json: async () => ({}) }));

		render(HDHomeRunPlayer, { props: seekableProps });

		const ccButton = await screen.findByRole('button', { name: 'Subtitles / Closed Captions' });
		// Initially off
		expect(screen.queryByText('Welcome to the show')).not.toBeInTheDocument();

		// Toggle captions on
		await fireEvent.click(ccButton);

		expect(await screen.findByText('Welcome to the show')).toBeInTheDocument();
		expect(screen.getByText('Enjoy the broadcast')).toBeInTheDocument();
		const overlay = document.querySelector('.caption-overlay');
		expect(overlay).toBeInTheDocument();
		expect(overlay).toHaveAttribute('aria-live', 'polite');

		// Advance video currentTime past cue end
		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 6, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		expect(screen.queryByText('Welcome to the show')).not.toBeInTheDocument();
	});

	it('eagerly discovers and loads captions for completed recordings even if detail has_captions was false', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 1200,
			video: null,
			audio: [],
			has_captions: false,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vtt = ['WEBVTT', '', '00:00:00.000 --> 00:00:05.000', 'Discovered Captions', ''].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt, json: async () => ({}) }));

		render(HDHomeRunPlayer, { props: seekableProps });

		// The CC button should appear once the 200 VTT is parsed
		const ccButton = await screen.findByRole('button', { name: 'Subtitles / Closed Captions' });
		expect(ccButton).toBeInTheDocument();

		await fireEvent.click(ccButton);
		expect(await screen.findByText('Discovered Captions')).toBeInTheDocument();
	});

	it('updates on-screen caption overlay when seeking through a recording', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 1200,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vtt = [
			'WEBVTT',
			'',
			'00:01:00.000 --> 00:01:05.000',
			'Scene at 1 minute',
			'',
			'00:05:00.000 --> 00:05:05.000',
			'Scene at 5 minutes',
			'',
		].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt, json: async () => ({}) }));
		vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
			left: 0,
			right: 1200,
			top: 0,
			bottom: 20,
			width: 1200,
			height: 20,
			x: 0,
			y: 0,
			toJSON: () => {},
		});

		render(HDHomeRunPlayer, { props: seekableProps });

		const ccButton = await screen.findByRole('button', { name: 'Subtitles / Closed Captions' });
		await fireEvent.click(ccButton);

		// Seek to 60s (1 minute)
		const scrubBar = await screen.findByRole('slider');
		await fireEvent.click(scrubBar, { clientX: 60 });

		expect(await screen.findByText('Scene at 1 minute')).toBeInTheDocument();
		expect(screen.queryByText('Scene at 5 minutes')).not.toBeInTheDocument();

		// Seek to 300s (5 minutes)
		await fireEvent.click(scrubBar, { clientX: 300 });

		expect(await screen.findByText('Scene at 5 minutes')).toBeInTheDocument();
		expect(screen.queryByText('Scene at 1 minute')).not.toBeInTheDocument();
	});

	it('renders stretched live captions in the on-screen overlay', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: true,
			duration_seconds: 30,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vttEmpty = 'WEBVTT\n\n';
		const vttLive = ['WEBVTT', '', '00:00:31.000 --> 00:00:32.000', 'Live Breaking News', ''].join('\n');
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, text: async () => vttEmpty })
			.mockResolvedValueOnce({ ok: true, text: async () => vttLive });
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props: seekableProps });

		const ccButton = await screen.findByRole('button', { name: 'Subtitles / Closed Captions' });
		await fireEvent.click(ccButton);

		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 5, configurable: true });
		Object.defineProperty(video, 'paused', { value: false, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		await vi.advanceTimersByTimeAsync(2_000);

		// Stretched cue starts at nowAbsolute = 30 + 5 = 35s, with currentTime = 5s (pos = 35s)
		expect(await screen.findByText('Live Breaking News')).toBeInTheDocument();

		vi.useRealTimers();
	});

	it('eagerly loads live captions while in progress, then appends only new cues on the next poll', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: true,
			duration_seconds: 30,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vttV1 = ['WEBVTT', '', '00:00:31.000 --> 00:00:32.000', 'First', ''].join('\n');
		const vttV2 = [vttV1, '00:00:33.000 --> 00:00:34.000', 'Second', ''].join('\n');
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, text: async () => vttV1 })
			.mockResolvedValueOnce({ ok: true, text: async () => vttV2 });
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		expect(fakeTextTrack.cues[0].text).toBe('First');

		// Live captions poll on their own faster interval, decoupled from the
		// heavier 5s detail poll, so they don't add avoidable extra latency
		// on top of whatever's already sitting in the backend's sidecar file.
		await vi.advanceTimersByTimeAsync(2_000);

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(2));
		expect(fakeTextTrack.cues[1].text).toBe('Second');

		vi.useRealTimers();
	});

	it('stretches a live cue that arrives already past its natural end so it can still render', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: true,
			duration_seconds: 30,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vttEmpty = 'WEBVTT\n\n';
		// Absolute 31-32s -> local 1-2s once baseOffsetSeconds (30) is applied,
		// well behind the currentTime we set below by the time it's fetched.
		const vttStale = ['WEBVTT', '', '00:00:31.000 --> 00:00:32.000', 'Stale', ''].join('\n');
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, text: async () => vttEmpty })
			.mockResolvedValueOnce({ ok: true, text: async () => vttStale });
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect(fakeTextTrack.cues).toHaveLength(0);

		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 10, configurable: true });
		Object.defineProperty(video, 'paused', { value: false, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		await vi.advanceTimersByTimeAsync(2_000);

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		// The cue's natural window (1-2s) is already behind currentTime (10s) by
		// the time it arrives, so instead of silently never activating it gets
		// rescheduled to start now and held for LIVE_CUE_MIN_DISPLAY_SECONDS.
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(10);
		expect(fakeTextTrack.cues[0].endTime).toBeCloseTo(14);

		vi.useRealTimers();
	});

	it('staggers several already-stale cues delivered in the same poll instead of stacking them', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: true,
			duration_seconds: 30,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vttEmpty = 'WEBVTT\n\n';
		// Both absolute cues (31-32s, 33-34s) are already behind the
		// currentTime set below, as if a backlog delivered them together.
		const vttStaleBurst = [
			'WEBVTT',
			'',
			'00:00:31.000 --> 00:00:32.000',
			'First',
			'',
			'00:00:33.000 --> 00:00:34.000',
			'Second',
			'',
		].join('\n');
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, text: async () => vttEmpty })
			.mockResolvedValueOnce({ ok: true, text: async () => vttStaleBurst });
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect(fakeTextTrack.cues).toHaveLength(0);

		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 10, configurable: true });
		Object.defineProperty(video, 'paused', { value: false, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		await vi.advanceTimersByTimeAsync(2_000);

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(2));
		// Both cues are stale on arrival, but instead of both piling up at
		// [10, 14] the second is pushed to start where the first's window
		// ends, so they play one after another instead of stacking as
		// multiple simultaneous lines.
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(10);
		expect(fakeTextTrack.cues[0].endTime).toBeCloseTo(14);
		expect(fakeTextTrack.cues[1].startTime).toBeCloseTo(14);
		expect(fakeTextTrack.cues[1].endTime).toBeCloseTo(18);

		vi.useRealTimers();
	});

	it('re-anchors each poll to now instead of drifting forward across separate polls', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: true,
			duration_seconds: 30,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vttEmpty = 'WEBVTT\n\n';
		// Both absolute cues (31-32s, 33-34s) are already stale relative to the
		// currentTime set below, but unlike the same-poll staggering test above,
		// each is delivered on its OWN separate poll - closer together than
		// LIVE_CUE_MIN_DISPLAY_SECONDS (4s) apart, mirroring real roll-up cadence
		// (observed as low as ~0.4-1s between consecutive cues in production).
		const vtt1 = ['WEBVTT', '', '00:00:31.000 --> 00:00:32.000', 'First', ''].join('\n');
		const vtt2 = [vtt1, '00:00:33.000 --> 00:00:34.000', 'Second', ''].join('\n');
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, text: async () => vttEmpty })
			.mockResolvedValueOnce({ ok: true, text: async () => vtt1 })
			.mockResolvedValueOnce({ ok: true, text: async () => vtt2 });
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect(fakeTextTrack.cues).toHaveLength(0);

		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 10, configurable: true });
		Object.defineProperty(video, 'paused', { value: false, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		await vi.advanceTimersByTimeAsync(1_000);
		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(10);
		expect(fakeTextTrack.cues[0].endTime).toBeCloseTo(14);

		await vi.advanceTimersByTimeAsync(1_000);
		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(2));
		// If the second cue's reservation carried over from the first poll's
		// nextStretchSlotAbsolute (14), it would queue at [14, 18] and every
		// later cue would drift further ahead of real time with each new poll,
		// never catching back up - the permanent-freeze bug. Anchoring fresh to
		// "now" on this separate poll instead puts it right alongside the
		// first cue, at [10, 14].
		expect(fakeTextTrack.cues[1].startTime).toBeCloseTo(10);
		expect(fakeTextTrack.cues[1].endTime).toBeCloseTo(14);

		vi.useRealTimers();
	});

	it('caps how far a large backlog burst of stale cues gets staggered into the future', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: true,
			duration_seconds: 30,
			video: null,
			audio: [],
			has_captions: true,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vttEmpty = 'WEBVTT\n\n';
		// A roll-up decoder that flushes a cue per line increment can hand
		// back a large backlog on the very first poll after enabling
		// captions mid-show (e.g. ccextractor's SRT output vs ffmpeg's
		// coarser per-completed-line cues). All ten are tightly packed and
		// well behind the currentTime set below, as if the whole backlog
		// arrived in one poll.
		const blocks = [];
		for (let i = 0; i < 10; i++) {
			const startS = (31 + i * 0.1).toFixed(3);
			const endS = (31.1 + i * 0.1).toFixed(3);
			blocks.push(`00:00:${startS} --> 00:00:${endS}`, `Cue${i}`, '');
		}
		const vttBacklog = ['WEBVTT', '', ...blocks].join('\n');
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, text: async () => vttEmpty })
			.mockResolvedValueOnce({ ok: true, text: async () => vttBacklog });
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect(fakeTextTrack.cues).toHaveLength(0);

		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 10, configurable: true });
		Object.defineProperty(video, 'paused', { value: false, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		await vi.advanceTimersByTimeAsync(2_000);

		// Every cue still lands in the track (history is preserved for
		// rewind), but only the leading run within
		// LIVE_CUE_MAX_CATCHUP_SECONDS (20s) of "now" (10s) gets staggered
		// forward - cues 0-5 (slots 10,14,...,30, i.e. up to +20 past now).
		// Past that, later backlog cues are left at their natural (already
		// past) timestamps instead of queuing the catch-up arbitrarily far
		// into the future - which is what previously made captions on a
		// large backlog read as "stopped after the first one."
		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(10));
		const stretchedStarts = [10, 14, 18, 22, 26, 30];
		for (let i = 0; i < stretchedStarts.length; i++) {
			expect(fakeTextTrack.cues[i].startTime).toBeCloseTo(stretchedStarts[i]);
			expect(fakeTextTrack.cues[i].endTime).toBeCloseTo(stretchedStarts[i] + 4);
		}
		// Cue 6 onward wasn't stretched - its natural start (1.6s = 31.6 - 30)
		// is well before "now" (10s), nowhere near the stretched queue.
		expect(fakeTextTrack.cues[6].startTime).toBeCloseTo(1.6);
		expect(fakeTextTrack.cues[6].startTime).toBeLessThan(stretchedStarts[stretchedStarts.length - 1]);

		vi.useRealTimers();
	});

	it('does not resurrect an already-expired cue when a resync rebuilds the track', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		hdhomerunRecordingDetail
			.mockResolvedValueOnce({
				is_in_progress: true,
				duration_seconds: 30,
				video: null,
				audio: [],
				has_captions: true,
				transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
			})
			.mockResolvedValue({
				is_in_progress: true,
				duration_seconds: 40,
				video: null,
				audio: [],
				has_captions: true,
				transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
			});
		// Absolute 31-32s -> local 1-2s, delivered while currentTime is still
		// 0 - not stale on arrival, so it renders normally and is never
		// given a stretched display window.
		const vtt = ['WEBVTT', '', '00:00:31.000 --> 00:00:32.000', 'Old', ''].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt }));

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(1);

		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 20, configurable: true });
		Object.defineProperty(video, 'paused', { value: false, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		await vi.advanceTimersByTimeAsync(5_000);

		// Corrected offset is 40 - 20 = 20, well past the drift threshold, so
		// refreshCaptionCues() rebuilds the track. The cue's window shifts
		// with the corrected offset (31 - 20 = 11, 32 - 20 = 12), but it must
		// NOT be treated as newly arrived and re-stretched to the new "now"
		// (20-24) - that's exactly what would flood the screen with the
		// whole transcript, active all at once, on every resync.
		await vi.waitFor(() => expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(11));
		expect(fakeTextTrack.cues[0].endTime).toBeCloseTo(12);
		expect(fakeTextTrack.cues).toHaveLength(1);

		vi.useRealTimers();
	});

	it('resyncs baseOffsetSeconds when it drifts from the actual playback position', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		// duration_seconds grows on every detail poll (wall clock elapsed
		// since capture start), same as a real in-progress recording.
		hdhomerunRecordingDetail
			.mockResolvedValueOnce({
				is_in_progress: true,
				duration_seconds: 30,
				video: null,
				audio: [],
				has_captions: true,
				transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
			})
			.mockResolvedValue({
				is_in_progress: true,
				duration_seconds: 33,
				video: null,
				audio: [],
				has_captions: true,
				transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
			});
		const vtt = ['WEBVTT', '', '00:00:31.000 --> 00:00:32.000', 'First', ''].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt }));

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		// baseOffsetSeconds started at 30, so the cue at absolute 31s renders at 1s.
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(1);

		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 5, configurable: true });
		Object.defineProperty(video, 'paused', { value: false, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		await vi.advanceTimersByTimeAsync(5_000);

		// Corrected offset is 33 - 5 = 28 (more than the 1.5s drift threshold
		// away from the original 30), so the cue re-renders at 31 - 28 = 3.
		await vi.waitFor(() => expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(3));

		vi.useRealTimers();
	});

	it('does not resync baseOffsetSeconds while playback is paused', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		hdhomerunRecordingDetail
			.mockResolvedValueOnce({
				is_in_progress: true,
				duration_seconds: 30,
				video: null,
				audio: [],
				has_captions: true,
				transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
			})
			.mockResolvedValue({
				is_in_progress: true,
				duration_seconds: 45,
				video: null,
				audio: [],
				has_captions: true,
				transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
			});
		const vtt = ['WEBVTT', '', '00:00:31.000 --> 00:00:32.000', 'First', ''].join('\n');
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, text: async () => vtt }));

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fakeTextTrack.cues).toHaveLength(1));
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(1);

		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 5, configurable: true });
		Object.defineProperty(video, 'paused', { value: true, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		await vi.advanceTimersByTimeAsync(5_000);

		// Still paused, so no resync should have happened - the cue stays at
		// its original position instead of drifting while nothing's playing.
		expect(fakeTextTrack.cues[0].startTime).toBeCloseTo(1);

		vi.useRealTimers();
	});

	it('shows the transcode preset (with a HW badge) in the playback-info panel', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 120,
			video: { codec: 'h264', width: 1280, height: 720, fps: 29.97 },
			audio: [],
			has_captions: false,
			transcode: {
				transcoding: true,
				preset: 'videotoolbox',
				preset_label: 'Apple VideoToolbox (macOS)',
				hardware: true,
			},
		});

		render(HDHomeRunPlayer, { props: seekableProps });

		const infoBtn = await screen.findByRole('button', { name: 'Playback Info' });
		await fireEvent.click(infoBtn);

		expect(await screen.findByText(/Transcoding via Apple VideoToolbox/)).toBeInTheDocument();
		expect(screen.getByText('HW')).toBeInTheDocument();
	});

	it('shows direct passthrough when server-side transcoding is disabled', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 120,
			video: { codec: 'h264', width: 1280, height: 720, fps: 29.97 },
			audio: [],
			has_captions: false,
			transcode: { transcoding: false, preset: null, preset_label: null, hardware: false },
		});

		render(HDHomeRunPlayer, { props: seekableProps });

		const infoBtn = await screen.findByRole('button', { name: 'Playback Info' });
		await fireEvent.click(infoBtn);

		expect(await screen.findByText('Direct passthrough')).toBeInTheDocument();
	});

	it('shows an analyzing placeholder while in progress before enough data exists to probe', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: true,
			duration_seconds: 5,
			video: null,
			audio: [],
			has_captions: false,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});

		render(HDHomeRunPlayer, { props: seekableProps });

		const infoBtn = await screen.findByRole('button', { name: 'Playback Info' });
		await fireEvent.click(infoBtn);

		expect(await screen.findByText('Analyzing stream…')).toBeInTheDocument();
	});

	it('renders Record button when playing a live channel and opens menu', async () => {
		const onRecordEpisode = vi.fn();
		const onRecordSeries = vi.fn();
		const channel = {
			channel_number: '4.1',
			name: 'KDFW',
			is_hd: true,
			is_drm: false,
			stream_url: 'http://tuner/auto/v4.1',
			playback_url: '/auto/v4.1',
			now: {
				title: 'Evening News',
				episode_title: 'Breaking Stories',
				series_id: 'SERIES123',
				start: 1700000000,
				end: 1700003600,
			},
			next: null,
		};

		render(HDHomeRunPlayer, {
			props: {
				...props,
				channel,
				airing: channel.now,
				onRecordEpisode,
				onRecordSeries,
			},
		});

		const recordBtn = screen.getByRole('button', { name: /Record/i });
		expect(recordBtn).toBeInTheDocument();

		await fireEvent.click(recordBtn);

		expect(screen.getByRole('button', { name: /Record Episode/i })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Record Series/i })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Recording options…/i })).toBeInTheDocument();
	});

	it('calls onRecordEpisode when Record Episode is clicked in the popover', async () => {
		const onRecordEpisode = vi.fn();
		const channel = {
			channel_number: '4.1',
			name: 'KDFW',
			is_hd: true,
			is_drm: false,
			stream_url: 'http://tuner/auto/v4.1',
			playback_url: '/auto/v4.1',
			now: {
				title: 'Evening News',
				episode_title: null,
				series_id: null,
				start: 1700000000,
				end: 1700003600,
			},
			next: null,
		};

		render(HDHomeRunPlayer, {
			props: {
				...props,
				channel,
				airing: channel.now,
				onRecordEpisode,
			},
		});

		const recordBtn = screen.getByRole('button', { name: /Record/i });
		await fireEvent.click(recordBtn);

		const episodeBtn = screen.getByRole('button', { name: /Record Episode/i });
		await fireEvent.click(episodeBtn);

		expect(onRecordEpisode).toHaveBeenCalledWith(null, '4.1', 1700000000, undefined);
	});

	it('calls onRecordSeries when Record Series is clicked in the popover', async () => {
		const onRecordSeries = vi.fn();
		const channel = {
			channel_number: '4.1',
			name: 'KDFW',
			is_hd: true,
			is_drm: false,
			stream_url: 'http://tuner/auto/v4.1',
			playback_url: '/auto/v4.1',
			now: {
				title: 'Evening News',
				episode_title: null,
				series_id: 'SERIES123',
				start: 1700000000,
				end: 1700003600,
			},
			next: null,
		};

		render(HDHomeRunPlayer, {
			props: {
				...props,
				channel,
				airing: channel.now,
				onRecordSeries,
			},
		});

		const recordBtn = screen.getByRole('button', { name: /Record/i });
		await fireEvent.click(recordBtn);

		const seriesBtn = screen.getByRole('button', { name: /Record Series/i });
		await fireEvent.click(seriesBtn);

		expect(onRecordSeries).toHaveBeenCalledWith('SERIES123', '4.1', undefined);
	});

	it('displays Recording state and triggers onCancelRule when active recording rule exists', async () => {
		const onCancelRule = vi.fn();
		const channel = {
			channel_number: '4.1',
			name: 'KDFW',
			is_hd: true,
			is_drm: false,
			stream_url: 'http://tuner/auto/v4.1',
			playback_url: '/auto/v4.1',
			now: {
				title: 'Evening News',
				episode_title: null,
				series_id: 'SERIES123',
				start: 1700000000,
				end: 1700003600,
			},
			next: null,
		};
		const recordingRules = [
			{
				RecordingRuleID: 'rule_abc123',
				SeriesID: 'SERIES123',
				Title: 'Evening News',
				ChannelOnly: '4.1',
			},
		];

		render(HDHomeRunPlayer, {
			props: {
				...props,
				channel,
				airing: channel.now,
				recordingRules,
				onCancelRule,
			},
		});

		const recordingBtn = screen.getByRole('button', { name: /Recording/i });
		expect(recordingBtn).toBeInTheDocument();
		expect(recordingBtn).toHaveClass('recording');

		await fireEvent.click(recordingBtn);

		const cancelBtn = screen.getByRole('button', { name: /Cancel Recording/i });
		await fireEvent.click(cancelBtn);

		expect(onCancelRule).toHaveBeenCalledWith('rule_abc123');
	});

	it('opens recording options dialog and confirms custom options', async () => {
		const onRecordEpisode = vi.fn();
		const channel = {
			channel_number: '4.1',
			name: 'KDFW',
			is_hd: true,
			is_drm: false,
			stream_url: 'http://tuner/auto/v4.1',
			playback_url: '/auto/v4.1',
			now: {
				title: 'Evening News',
				episode_title: null,
				series_id: null,
				start: 1700000000,
				end: 1700003600,
			},
			next: null,
		};

		render(HDHomeRunPlayer, {
			props: {
				...props,
				channel,
				airing: channel.now,
				onRecordEpisode,
			},
		});

		const recordBtn = screen.getByRole('button', { name: /Record/i });
		await fireEvent.click(recordBtn);

		const optionsBtn = screen.getByRole('button', { name: /Recording options…/i });
		await fireEvent.click(optionsBtn);

		expect(screen.getByRole('dialog', { name: /Recording Options/i })).toBeInTheDocument();

		const confirmBtn = screen.getByRole('button', { name: /Record Episode/i });
		await fireEvent.click(confirmBtn);

		expect(onRecordEpisode).toHaveBeenCalled();
	});

	it('falls back to direct API call when onRecordEpisode prop is omitted', async () => {
		addHDHomeRunRecordingRule.mockResolvedValue([]);
		const channel = {
			channel_number: '4.1',
			name: 'KDFW',
			is_hd: true,
			is_drm: false,
			stream_url: 'http://tuner/auto/v4.1',
			playback_url: '/auto/v4.1',
			now: {
				title: 'Evening News',
				episode_title: null,
				series_id: null,
				start: 1700000000,
				end: 1700003600,
			},
			next: null,
		};

		render(HDHomeRunPlayer, {
			props: {
				...props,
				channel,
				airing: channel.now,
			},
		});

		const recordBtn = screen.getByRole('button', { name: /Record/i });
		await fireEvent.click(recordBtn);

		const episodeBtn = screen.getByRole('button', { name: /Record Episode/i });
		await fireEvent.click(episodeBtn);

		expect(addHDHomeRunRecordingRule).toHaveBeenCalledWith(
			expect.objectContaining({
				channel: '4.1',
				date_time: 1700000000,
			}),
		);
	});

	it('does not render Record button during seekable recorded file playback', () => {
		render(HDHomeRunPlayer, { props: seekableProps });
		expect(screen.queryByRole('button', { name: /^Record/i })).not.toBeInTheDocument();
	});
});
