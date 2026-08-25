export interface ThumbnailCue {
	startSeconds: number;
	endSeconds: number;
	x: number;
	y: number;
	w: number;
	h: number;
}

export function parseThumbnailVtt(text: string): ThumbnailCue[] {
	const cues: ThumbnailCue[] = [];
	const timeToSeconds = (ts: string): number => {
		const match = ts.match(/(\d+):(\d+):(\d+(?:\.\d+)?)/);
		if (!match) return 0;
		return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
	};
	const blocks = text.split(/\r?\n\r?\n/);
	for (const block of blocks) {
		const lines = block.split(/\r?\n/).filter((l) => l.trim());
		const cueLine = lines.find((l) => l.includes('-->'));
		const xywhLine = lines.find((l) => l.includes('#xywh='));
		if (!cueLine || !xywhLine) continue;
		const [startRaw, endRaw] = cueLine.split('-->').map((s) => s.trim());
		const xywhMatch = xywhLine.match(/#xywh=(\d+),(\d+),(\d+),(\d+)/);
		if (!xywhMatch) continue;
		cues.push({
			startSeconds: timeToSeconds(startRaw),
			endSeconds: timeToSeconds(endRaw),
			x: Number(xywhMatch[1]),
			y: Number(xywhMatch[2]),
			w: Number(xywhMatch[3]),
			h: Number(xywhMatch[4]),
		});
	}
	return cues;
}

export interface CaptionCue {
	start: number;
	end: number;
	text: string;
	// Set once, only when this cue first arrives already past its natural
	// end (see LIVE_CUE_MIN_DISPLAY_SECONDS in caption-controller.svelte.ts) -
	// the stretched window it was given, in the same absolute
	// (capture-start-relative) basis as start/end so it survives
	// baseOffsetSeconds changing on a later resync instead of being
	// re-decided (and re-triggered) against whatever currentTime happens to
	// be at rebuild time.
	displayStart?: number;
	displayEnd?: number;
}

export function parseVttTimestamp(raw: string): number {
	const parts = raw.trim().split(':');
	if (parts.length === 3) {
		return Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2]);
	} else if (parts.length === 2) {
		return Number(parts[0]) * 60 + Number(parts[1]);
	} else if (parts.length === 1) {
		return Number(parts[0]) || 0;
	}
	return 0;
}

export function parseCaptionsVtt(text: string): CaptionCue[] {
	const cues: CaptionCue[] = [];
	const blocks = text.replace(/\r\n/g, '\n').split(/\n\n+/);
	for (const block of blocks) {
		const lines = block.split('\n').filter((l) => l.length > 0);
		const cueLineIndex = lines.findIndex((l) => l.includes('-->'));
		if (cueLineIndex === -1) continue;
		const [startRaw, endRaw] = lines[cueLineIndex].split('-->');
		const start = parseVttTimestamp(startRaw);
		const end = parseVttTimestamp(endRaw.trim().split(/\s+/)[0]);
		const textLines = lines.slice(cueLineIndex + 1);
		if (textLines.length === 0) continue;
		// ffmpeg's CEA-608 decoder writes the literal two characters "\h"
		// for a caption-positioning space code (used for indentation)
		// instead of an actual space - a run of "\h\h\h\h" is just
		// indentation that never got converted to real whitespace, so
		// swap it for a real space so it reads as normal text instead of
		// showing the literal escape code. Also strip any WebVTT tags.
		const cleanedText = textLines
			.join('\n')
			.replace(/\\h/g, ' ')
			.replace(/<[^>]+>/g, '');
		if (!cleanedText.trim()) continue;
		cues.push({ start, end, text: cleanedText });
	}
	return cues;
}
