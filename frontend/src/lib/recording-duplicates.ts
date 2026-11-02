import type { HDHomeRunRecording, HDHomeRunRecordingDuplicateGroup } from '$lib/api';

function idsOf(group: HDHomeRunRecordingDuplicateGroup): string[] {
	return group.recordings.map((r) => r.recording_id).filter((id): id is string => Boolean(id));
}

/** Every recording starts checked for deletion except each group's suggested keeper. */
export function initialSelection(groups: HDHomeRunRecordingDuplicateGroup[]): Set<string> {
	const selected = new Set<string>();
	for (const group of groups) {
		for (const id of idsOf(group)) {
			if (id !== group.suggested_keep_id) selected.add(id);
		}
	}
	return selected;
}

/** Keys of groups where every copy is checked, i.e. nothing would be kept. */
export function groupsWithAllSelected(
	groups: HDHomeRunRecordingDuplicateGroup[],
	selected: ReadonlySet<string>,
): Set<string> {
	return new Set(
		groups
			.filter((g) => {
				const ids = idsOf(g);
				return ids.length > 0 && ids.every((id) => selected.has(id));
			})
			.map((g) => g.key),
	);
}

/** How many recordings are checked and how many bytes deleting them frees. */
export function selectionSummary(
	groups: HDHomeRunRecordingDuplicateGroup[],
	selected: ReadonlySet<string>,
): { count: number; bytes: number } {
	const byId = new Map<string, HDHomeRunRecording>();
	for (const group of groups) {
		for (const rec of group.recordings) {
			if (rec.recording_id) byId.set(rec.recording_id, rec);
		}
	}
	let count = 0;
	let bytes = 0;
	for (const id of selected) {
		const rec = byId.get(id);
		if (!rec) continue;
		count += 1;
		bytes += rec.file_size_bytes ?? 0;
	}
	return { count, bytes };
}
