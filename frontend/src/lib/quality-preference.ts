export type QualityPreference = 'auto' | 'high' | 'medium' | 'low';

const QUALITY_KEY = 'hdhomerun_quality_preference';
const VALID_VALUES: QualityPreference[] = ['auto', 'high', 'medium', 'low'];

export function getQualityPreference(): QualityPreference {
	if (typeof localStorage === 'undefined') return 'auto';
	try {
		const value = localStorage.getItem(QUALITY_KEY);
		return VALID_VALUES.includes(value as QualityPreference) ? (value as QualityPreference) : 'auto';
	} catch {
		return 'auto';
	}
}

export function setQualityPreference(quality: QualityPreference): void {
	if (typeof localStorage === 'undefined') return;
	try {
		if (quality === 'auto') {
			localStorage.removeItem(QUALITY_KEY);
		} else {
			localStorage.setItem(QUALITY_KEY, quality);
		}
	} catch {
		// Ignore storage access errors in restricted contexts
	}
}
