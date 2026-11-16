// Per-browser "resume where you left off" positions for completed
// recordings, keyed by recording id (or play URL when there's no id).
// Purely a convenience: every read/write is wrapped so a blocked or broken
// localStorage just means "start from the beginning", never an error.

const STORAGE_KEY = 'hdhr_resume_positions';
const MAX_ENTRIES = 200;
// Below this, the user barely started - not worth resuming.
export const MIN_RESUME_SECONDS = 15;
// Within this many seconds of the end (or past FINISHED_RATIO of the
// duration), the recording counts as finished and restarts from 0.
export const FINISHED_TAIL_SECONDS = 60;
export const FINISHED_RATIO = 0.95;

interface ResumeEntry {
	position: number;
	duration: number | null;
	updatedAt: number;
}

type ResumeMap = Record<string, ResumeEntry>;

export function resumeKeyFor(media: { recordingId?: string | null; playUrl?: string | null }): string | null {
	return media.recordingId || media.playUrl || null;
}

function readMap(): ResumeMap {
	if (typeof localStorage === 'undefined') return {};
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return {};
		const parsed: unknown = JSON.parse(raw);
		return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as ResumeMap) : {};
	} catch {
		return {};
	}
}

function writeMap(map: ResumeMap): void {
	if (typeof localStorage === 'undefined') return;
	try {
		const keys = Object.keys(map);
		if (keys.length > MAX_ENTRIES) {
			keys
				.sort((a, b) => (map[b].updatedAt ?? 0) - (map[a].updatedAt ?? 0))
				.slice(MAX_ENTRIES)
				.forEach((k) => delete map[k]);
		}
		localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
	} catch {
		// Ignore storage access/quota errors
	}
}

function isResumable(position: number, duration: number | null): boolean {
	if (!Number.isFinite(position) || position < MIN_RESUME_SECONDS) return false;
	if (duration !== null && Number.isFinite(duration) && duration > 0) {
		if (position >= duration - FINISHED_TAIL_SECONDS) return false;
		if (position >= duration * FINISHED_RATIO) return false;
	}
	return true;
}

export function saveResumePosition(key: string | null, position: number, duration: number | null): void {
	if (!key) return;
	const map = readMap();
	if (!isResumable(position, duration)) {
		if (key in map) {
			delete map[key];
			writeMap(map);
		}
		return;
	}
	map[key] = { position, duration, updatedAt: Date.now() };
	writeMap(map);
}

export function getResumePosition(key: string | null, duration: number | null): number | null {
	if (!key) return null;
	const entry = readMap()[key];
	if (!entry || typeof entry.position !== 'number') return null;
	return isResumable(entry.position, duration ?? entry.duration ?? null) ? entry.position : null;
}

export function clearResumePosition(key: string | null): void {
	if (!key) return;
	const map = readMap();
	if (!(key in map)) return;
	delete map[key];
	writeMap(map);
}
