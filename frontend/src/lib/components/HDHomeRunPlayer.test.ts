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
	createChannelHlsSessionForCast,
	createRecordingHlsSessionForCast,
	stopHlsSession,
} = vi.hoisted(() => ({
	hdhomerunRecordingStreamUrl: vi.fn(
		(playUrl: string, options?: { start?: number; audioIndex?: number; recordingId?: string | null }) =>
			`https://example.com/recording-stream?url=${playUrl}&start=${options?.start ?? ''}&audio=${options?.audioIndex ?? ''}`,
	),
	hdhomerunRecordingDetail: vi.fn(),
	hdhomerunRecordingCaptionsUrl: vi.fn(
		(opts: { recordingId: string; track?: 1 | 2 }) =>
			`https://example.com/captions/${opts.recordingId}.vtt${opts.track && opts.track !== 1 ? `?track=${opts.track}` : ''}`,
	),
	hdhomerunRecordingThumbnailVttUrl: vi.fn(
		(opts: { recordingId: string }) => `https://example.com/thumbs/${opts.recordingId}.vtt`,
	),
	hdhomerunRecordingThumbnailSpriteUrl: vi.fn(
		(opts: { recordingId: string }) => `https://example.com/thumbs/${opts.recordingId}.jpg`,
	),
	addHDHomeRunRecordingRule: vi.fn(),
	deleteHDHomeRunRecordingRule: vi.fn(),
	createChannelHlsSessionForCast: vi.fn(async (channelNumber: string) => ({
		session_id: `sess-${channelNumber}`,
		playlist_url: `https://example.com/api/hls/sess-${channelNumber}/tok/playlist.m3u8`,
	})),
	createRecordingHlsSessionForCast: vi.fn(async () => ({
		session_id: 'sess-rec1',
		playlist_url: 'https://example.com/api/hls/sess-rec1/tok/playlist.m3u8',
	})),
	stopHlsSession: vi.fn(),
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
		createChannelHlsSessionForCast,
		createRecordingHlsSessionForCast,
		stopHlsSession,
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
import { setActiveCastSessionId } from '$lib/cast/cast-loader';

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
		setActiveCastSessionId(null);
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

	it('does not render a caption-track picker for a finished recording (secondary_captions is null)', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: false,
			duration_seconds: 1200,
			video: null,
			audio: [],
			has_captions: true,
			secondary_captions: null,
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue({ ok: true, text: async () => 'WEBVTT\n\n', json: async () => ({}) }),
		);

		render(HDHomeRunPlayer, { props: seekableProps });

		await screen.findByRole('button', { name: 'Subtitles / Closed Captions' });
		expect(screen.queryByRole('button', { name: 'CC Track' })).not.toBeInTheDocument();
	});

	it('lets the user switch to caption Track 2 on a live recording, resetting cues to the new track', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: true,
			duration_seconds: 30,
			video: null,
			audio: [],
			has_captions: true,
			secondary_captions: 'available',
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const vttTrack1 = ['WEBVTT', '', '00:00:01.000 --> 00:00:03.000', 'Track 1 line', ''].join('\n');
		const vttTrack2 = ['WEBVTT', '', '00:00:01.000 --> 00:00:03.000', 'Track 2 line', ''].join('\n');
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: true, text: async () => vttTrack1 })
			.mockResolvedValueOnce({ ok: true, text: async () => vttTrack2 });
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props: seekableProps });

		await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
		expect(fetchMock.mock.calls[0][0]).not.toMatch(/track=/);

		const trackMenuBtn = await screen.findByRole('button', { name: 'CC Track' });
		await fireEvent.click(trackMenuBtn);
		const track2Btn = screen.getByRole('button', { name: /Track 2/ });
		expect(track2Btn).not.toBeDisabled();
		await fireEvent.click(track2Btn);

		await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
		expect(fetchMock.mock.calls[1][0]).toMatch(/track=2/);

		// Enable the overlay and confirm only the new track's cue is showing.
		const ccButton = screen.getByRole('button', { name: 'Subtitles / Closed Captions' });
		await fireEvent.click(ccButton);
		const video = document.querySelector('video')!;
		Object.defineProperty(video, 'currentTime', { value: 2, configurable: true });
		await fireEvent(video, new Event('timeupdate'));

		expect(await screen.findByText('Track 2 line')).toBeInTheDocument();
		expect(screen.queryByText('Track 1 line')).not.toBeInTheDocument();
	});

	it('disables Track 2 in the picker when secondary_captions is unavailable', async () => {
		hdhomerunRecordingDetail.mockResolvedValue({
			is_in_progress: true,
			duration_seconds: 30,
			video: null,
			audio: [],
			has_captions: true,
			secondary_captions: 'unavailable',
			transcode: { transcoding: true, preset: 'software', preset_label: 'Software (libx264)', hardware: false },
		});
		const fetchMock = vi.fn().mockResolvedValue({ ok: true, text: async () => 'WEBVTT\n\n' });
		vi.stubGlobal('fetch', fetchMock);

		render(HDHomeRunPlayer, { props: seekableProps });

		const trackMenuBtn = await screen.findByRole('button', { name: 'CC Track' });
		await fireEvent.click(trackMenuBtn);
		const track2Btn = screen.getByRole('button', { name: /Track 2/ });
		expect(track2Btn).toBeDisabled();

		const callsBeforeClick = fetchMock.mock.calls.length;
		await fireEvent.click(track2Btn);
		// Disabled button click is a no-op - no extra fetch for a track switch.
		expect(fetchMock.mock.calls.length).toBe(callsBeforeClick);
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

	describe('AirPlay', () => {
		it('stays hidden until webkitplaybacktargetavailabilitychanged reports a route, then swaps to a real HLS playlist and opens the picker on click', async () => {
			// Feature-detected the same way Safari itself exposes AirPlay - other
			// browsers never define this, so the button never appears there.
			vi.stubGlobal('WebKitPlaybackTargetAvailabilityEvent', class {});
			vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
			vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
			const showPicker = vi.fn();
			(
				HTMLVideoElement.prototype as unknown as { webkitShowPlaybackTargetPicker: () => void }
			).webkitShowPlaybackTargetPicker = showPicker;

			render(HDHomeRunPlayer, {
				props: {
					...props,
					channel: {
						channel_number: '4.1',
						name: 'KDFW',
						is_hd: true,
						is_drm: false,
						stream_url: '',
						playback_url: null,
						now: null,
						next: null,
					},
				},
			});
			expect(screen.queryByRole('button', { name: 'AirPlay' })).not.toBeInTheDocument();

			// The overlay is use:portal-ed onto document.body (see JellyfinPlayer.svelte),
			// so it lives outside render()'s own container.
			const video = document.body.querySelector('video')!;
			// Let the initial mount's local mpegts.js attachment finish first,
			// so the later assertion can tell a fresh re-attachment apart from
			// this one.
			await vi.waitFor(() => expect(createPlayer).toHaveBeenCalledTimes(1));
			const availabilityEvent = new Event('webkitplaybacktargetavailabilitychanged');
			(availabilityEvent as unknown as { availability: string }).availability = 'available';
			await fireEvent(video, availabilityEvent);

			const airplayBtn = await screen.findByRole('button', { name: 'AirPlay' });
			await fireEvent.click(airplayBtn);

			// Regression guard: mpegts.js attaches via MediaSource (a blob:
			// <video> src), which an Apple TV can't fetch on its own - AirPlay
			// connects but nothing plays. The element must be swapped to a
			// directly-fetchable for_cast HLS URL - and, per a second
			// regression this swap must happen *before* the picker opens, not
			// after a route goes live: doing it after actually killed
			// playback everywhere (confirmed against real Safari/Apple TV),
			// since changing src/calling load() while a wireless route is
			// already active doesn't hand off cleanly, it just drops the
			// route.
			await vi.waitFor(() => expect(createChannelHlsSessionForCast).toHaveBeenCalledWith('4.1'));
			await vi.waitFor(() =>
				expect(video.src).toBe('https://example.com/api/hls/sess-4.1/tok/playlist.m3u8'),
			);
			await vi.waitFor(() => expect(showPicker).toHaveBeenCalledTimes(1));
		});

		it('reverts to the local mpegts.js pipeline once AirPlay disconnects', async () => {
			vi.stubGlobal('WebKitPlaybackTargetAvailabilityEvent', class {});
			vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
			vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
			(
				HTMLVideoElement.prototype as unknown as { webkitShowPlaybackTargetPicker: () => void }
			).webkitShowPlaybackTargetPicker = vi.fn();

			render(HDHomeRunPlayer, {
				props: {
					...props,
					channel: {
						channel_number: '4.1',
						name: 'KDFW',
						is_hd: true,
						is_drm: false,
						stream_url: '',
						playback_url: null,
						now: null,
						next: null,
					},
				},
			});

			const video = document.body.querySelector('video')! as HTMLVideoElement & {
				webkitCurrentPlaybackTargetIsWireless?: boolean;
			};
			await vi.waitFor(() => expect(createPlayer).toHaveBeenCalledTimes(1));
			const availabilityEvent = new Event('webkitplaybacktargetavailabilitychanged');
			(availabilityEvent as unknown as { availability: string }).availability = 'available';
			await fireEvent(video, availabilityEvent);
			const airplayBtn = await screen.findByRole('button', { name: 'AirPlay' });
			await fireEvent.click(airplayBtn);
			await vi.waitFor(() =>
				expect(video.src).toBe('https://example.com/api/hls/sess-4.1/tok/playlist.m3u8'),
			);

			video.webkitCurrentPlaybackTargetIsWireless = false;
			await fireEvent(video, new Event('webkitcurrentplaybacktargetiswirelesschanged'));

			await vi.waitFor(() => expect(stopHlsSession).toHaveBeenCalledWith('sess-4.1'));
			// Reverting re-attaches the local mpegts.js pipeline rather than
			// leaving the native HLS src in place.
			await vi.waitFor(() => expect(createPlayer).toHaveBeenCalledTimes(2));
		});
	});

	describe('Google Cast', () => {
		// jsdom doesn't implement HTMLMediaElement.play()/pause() - real
		// browsers return a real Promise from play(), which the
		// onCastingChange handler below relies on.
		beforeEach(() => {
			vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
			vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
		});

		// A minimal fake of the slice of window.cast/window.chrome.cast that
		// cast-loader.ts touches - see that file's local ambient Window typing
		// for the exact surface being stood in for here.
		function makeFakeCastGlobals(initialState: string) {
			let state = initialState;
			let session: { loadMedia: ReturnType<typeof vi.fn> } | null = null;
			const stateListeners: Array<(event: { castState: string }) => void> = [];
			const notify = () => stateListeners.forEach((listener) => listener({ castState: state }));
			class FakeMediaInfo {
				metadata?: { title?: string; subtitle?: string; images?: unknown[] };
				constructor(
					public contentUrl: string,
					public contentType: string,
				) {}
			}
			class FakeLoadRequest {
				constructor(public media: FakeMediaInfo) {}
			}
			const context = {
				setOptions: vi.fn(),
				getCurrentSession: () => session,
				requestSession: vi.fn(async () => {
					state = 'connected';
					session = { loadMedia: vi.fn(async () => {}) };
					notify();
				}),
				endCurrentSession: vi.fn(() => {
					state = 'not_connected';
					session = null;
					notify();
				}),
				getCastState: () => state,
				addEventListener: (_type: string, listener: (event: { castState: string }) => void) => {
					stateListeners.push(listener);
				},
				removeEventListener: vi.fn(),
			};
			return {
				context,
				cast: {
					framework: {
						CastContext: { getInstance: () => context },
						CastContextEventType: { CAST_STATE_CHANGED: 'caststatechanged' },
					},
				},
				chrome: {
					cast: {
						media: {
							DEFAULT_MEDIA_RECEIVER_APP_ID: 'CC1AD845',
							MediaInfo: FakeMediaInfo,
							GenericMediaMetadata: class {
								title?: string;
								subtitle?: string;
								images?: unknown[];
							},
							LoadRequest: FakeLoadRequest,
						},
						Image: class {
							constructor(public url: string) {}
						},
						AutoJoinPolicy: { ORIGIN_SCOPED: 'origin_scoped' },
					},
				},
			};
		}

		it('stays hidden with no receiver on the network', () => {
			render(HDHomeRunPlayer, {
				props: {
					...props,
					channel: {
						channel_number: '4.1',
						name: 'KDFW',
						is_hd: true,
						is_drm: false,
						stream_url: '',
						playback_url: null,
						now: null,
						next: null,
					},
				},
			});
			expect(screen.queryByRole('button', { name: 'Cast' })).not.toBeInTheDocument();
		});

		it('loads the for_cast HLS playlist onto the receiver once a device is available', async () => {
			const fake = makeFakeCastGlobals('not_connected');
			vi.stubGlobal('cast', fake.cast);
			vi.stubGlobal('chrome', fake.chrome);

			render(HDHomeRunPlayer, {
				props: {
					...props,
					channel: {
						channel_number: '4.1',
						name: 'KDFW',
						is_hd: true,
						is_drm: false,
						stream_url: '',
						playback_url: null,
						now: null,
						next: null,
					},
				},
			});

			const castBtn = await screen.findByRole('button', { name: 'Cast' });
			await fireEvent.click(castBtn);

			await vi.waitFor(() => expect(createChannelHlsSessionForCast).toHaveBeenCalledWith('4.1'));
			await vi.waitFor(() =>
				expect(fake.context.getCurrentSession()?.loadMedia).toHaveBeenCalledWith(
					expect.objectContaining({
						media: expect.objectContaining({
							contentUrl: 'https://example.com/api/hls/sess-4.1/tok/playlist.m3u8',
						}),
					}),
				),
			);
			expect(await screen.findByRole('button', { name: 'Stop Casting' })).toBeInTheDocument();
		});

		it('requests the Cast session before minting the (slow) backend HLS session, not after', async () => {
			// Regression guard: requestSession() opens Chrome's native device
			// picker, which only works while the click's user-activation is
			// still live. Previously this app awaited the backend HLS-session
			// call (which can take several real seconds while ffmpeg spins up)
			// *before* calling requestSession() - by the time it ran, the
			// picker's gesture window had expired, requestSession() never
			// resolved, and the button hung on "Connecting..." forever. Model
			// that slowness here with a delayed backend response and assert
			// requestSession() is still called (and resolves) first.
			const fake = makeFakeCastGlobals('not_connected');
			vi.stubGlobal('cast', fake.cast);
			vi.stubGlobal('chrome', fake.chrome);
			let resolveBackendCall!: () => void;
			createChannelHlsSessionForCast.mockImplementationOnce(
				(channelNumber: string) =>
					new Promise((resolve) => {
						resolveBackendCall = () =>
							resolve({
								session_id: `sess-${channelNumber}`,
								playlist_url: `https://example.com/api/hls/sess-${channelNumber}/tok/playlist.m3u8`,
							});
					}),
			);

			render(HDHomeRunPlayer, {
				props: {
					...props,
					channel: {
						channel_number: '4.1',
						name: 'KDFW',
						is_hd: true,
						is_drm: false,
						stream_url: '',
						playback_url: null,
						now: null,
						next: null,
					},
				},
			});

			const castBtn = await screen.findByRole('button', { name: 'Cast' });
			await fireEvent.click(castBtn);

			// The device picker (requestSession) must already have resolved -
			// and the receiver session must already exist - well before the
			// backend call is allowed to finish, proving it wasn't blocked
			// behind that slow await.
			await vi.waitFor(() => expect(fake.context.requestSession).toHaveBeenCalledTimes(1));
			expect(fake.context.getCurrentSession()).not.toBeNull();

			resolveBackendCall();
			await vi.waitFor(() =>
				expect(fake.context.getCurrentSession()?.loadMedia).toHaveBeenCalledTimes(1),
			);
		});

		it('keeps casting alive across an SPA navigation (component unmount), and lets a freshly-mounted player stop it', async () => {
			// Regression guard: CastButton's onDestroy used to unconditionally
			// call endCastSession()/stop the backend session whenever it
			// unmounted - which happens on every client-side route navigation
			// away from the player, not just when the user actually wants to
			// stop casting. window.cast's CastContext is page-scoped and
			// survives navigation on its own; the backend session id is now
			// tracked at module scope (cast-loader.ts) so a CastButton mounted
			// on a later page can still discover and stop the right session.
			const fake = makeFakeCastGlobals('not_connected');
			vi.stubGlobal('cast', fake.cast);
			vi.stubGlobal('chrome', fake.chrome);

			const { unmount } = render(HDHomeRunPlayer, {
				props: {
					...props,
					channel: {
						channel_number: '4.1',
						name: 'KDFW',
						is_hd: true,
						is_drm: false,
						stream_url: '',
						playback_url: null,
						now: null,
						next: null,
					},
				},
			});

			const castBtn = await screen.findByRole('button', { name: 'Cast' });
			await fireEvent.click(castBtn);
			await vi.waitFor(() => expect(fake.context.getCurrentSession()?.loadMedia).toHaveBeenCalledTimes(1));

			unmount();
			expect(stopHlsSession).not.toHaveBeenCalled();
			expect(fake.context.endCurrentSession).not.toHaveBeenCalled();
			// Still connected as far as the Cast SDK itself is concerned.
			expect(fake.context.getCastState()).toBe('connected');

			// A CastButton mounted on a different "page" after navigation.
			render(HDHomeRunPlayer, {
				props: {
					...props,
					channel: {
						channel_number: '5.1',
						name: 'KXAS',
						is_hd: true,
						is_drm: false,
						stream_url: '',
						playback_url: null,
						now: null,
						next: null,
					},
				},
			});

			const stopBtn = await screen.findByRole('button', { name: 'Stop Casting' });
			await fireEvent.click(stopBtn);

			await vi.waitFor(() => expect(stopHlsSession).toHaveBeenCalledWith('sess-4.1'));
		});
	});

	describe('Jellyfin Player UI & Controls', () => {
		it('toggles play/pause and center flash animation on click and Space key', async () => {
			render(HDHomeRunPlayer, { props: seekableProps });

			const playBtn = screen.getByRole('button', { name: /Pause/i });
			expect(playBtn).toBeInTheDocument();

			const videoContainer = screen.getByRole('button', { name: '' });
			await fireEvent.click(videoContainer);

			// Space key toggles play/pause
			await fireEvent.keyDown(window, { key: ' ' });
		});

		it('calculates dynamic Ends at timestamp for seekable recordings and LIVE for live channels', async () => {
			hdhomerunRecordingDetail.mockResolvedValue({
				is_in_progress: false,
				duration_seconds: 7200,
				video: null,
				audio: [],
				has_captions: false,
				transcode: { transcoding: false, preset: '', preset_label: '', hardware: false },
			});

			render(HDHomeRunPlayer, { props: seekableProps });
			expect(await screen.findByText(/Ends at/i)).toBeInTheDocument();
		});

		it('supports Fullscreen toggle via button and F key', async () => {
			const requestFullscreen = vi.fn().mockResolvedValue(undefined);
			const exitFullscreen = vi.fn().mockResolvedValue(undefined);
			HTMLElement.prototype.requestFullscreen = requestFullscreen;
			document.exitFullscreen = exitFullscreen;

			render(HDHomeRunPlayer, { props: seekableProps });

			const fsBtn = screen.getByRole('button', { name: /Fullscreen/i });
			await fireEvent.click(fsBtn);
			expect(requestFullscreen).toHaveBeenCalled();

			await fireEvent.keyDown(window, { key: 'f' });
		});

		it('supports Picture-in-Picture toggle via button and P key when supported', async () => {
			Object.defineProperty(document, 'pictureInPictureEnabled', { value: true, configurable: true });
			const requestPiP = vi.fn().mockResolvedValue({});
			HTMLVideoElement.prototype.requestPictureInPicture = requestPiP;

			render(HDHomeRunPlayer, { props: seekableProps });

			const pipBtn = await screen.findByRole('button', { name: /Picture in Picture/i });
			await fireEvent.click(pipBtn);
			expect(requestPiP).toHaveBeenCalled();

			await fireEvent.keyDown(window, { key: 'p' });
		});

		it('toggles mute and persists volume', async () => {
			render(HDHomeRunPlayer, { props: seekableProps });

			const muteBtn = screen.getByRole('button', { name: /Mute/i });
			await fireEvent.click(muteBtn);
			expect(screen.getByRole('button', { name: /Unmute/i })).toBeInTheDocument();

			await fireEvent.keyDown(window, { key: 'm' });
			expect(screen.getByRole('button', { name: /Mute/i })).toBeInTheDocument();
		});

		it('opens Settings menu and allows changing playback rate', async () => {
			render(HDHomeRunPlayer, { props: seekableProps });

			const settingsBtn = screen.getByRole('button', { name: /Settings/i });
			await fireEvent.click(settingsBtn);

			expect(screen.getByText(/Playback Settings/i)).toBeInTheDocument();
			const speedBtn = screen.getByRole('button', { name: /Speed/i });
			await fireEvent.click(speedBtn);

			const speed15 = screen.getByRole('button', { name: /1.5x/i });
			await fireEvent.click(speed15);
		});

		it('opens and closes SyncPlay modal', async () => {
			render(HDHomeRunPlayer, { props: seekableProps });

			const syncplayBtn = screen.getByRole('button', { name: /SyncPlay/i });
			await fireEvent.click(syncplayBtn);

			expect(screen.getByText('SyncPlay Watch Party')).toBeInTheDocument();
			const createBtn = screen.getByRole('button', { name: /Create New Watch Room/i });
			await fireEvent.click(createBtn);

			expect(screen.getByText(/Room Code:/i)).toBeInTheDocument();
			const leaveBtn = screen.getByRole('button', { name: /Leave Room/i });
			await fireEvent.click(leaveBtn);
		});
	});
});
