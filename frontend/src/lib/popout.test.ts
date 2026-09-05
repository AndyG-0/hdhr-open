import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
	buildPopoutUrl,
	openPopoutPlayer,
	POPOUT_WINDOW_TARGET,
	POPOUT_WINDOW_FEATURES,
} from './popout';

describe('popout utility', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
	});

	describe('buildPopoutUrl', () => {
		it('builds URL with channel', () => {
			expect(buildPopoutUrl({ channel: '5.1' })).toBe('/player?channel=5.1');
		});

		it('builds URL with recording', () => {
			expect(buildPopoutUrl({ recording: 'rec-123' })).toBe('/player?recording=rec-123');
		});

		it('builds URL with playUrl', () => {
			expect(buildPopoutUrl({ playUrl: '/auto/v5.1' })).toBe('/player?play_url=%2Fauto%2Fv5.1');
		});

		it('builds URL with title and playback time', () => {
			const url = buildPopoutUrl({
				channel: '5.1',
				title: 'Action News',
				t: 125.7,
			});
			expect(url).toBe('/player?channel=5.1&title=Action+News&t=125');
		});

		it('omits t when t is 0 or negative', () => {
			expect(buildPopoutUrl({ channel: '5.1', t: 0 })).toBe('/player?channel=5.1');
			expect(buildPopoutUrl({ channel: '5.1', t: -10 })).toBe('/player?channel=5.1');
		});
	});

	describe('openPopoutPlayer', () => {
		it('calls window.open with correct URL, target, and features', () => {
			const openMock = vi.fn();
			vi.stubGlobal('open', openMock);

			openPopoutPlayer({ channel: '7.1', title: 'PBS' });

			expect(openMock).toHaveBeenCalledWith(
				'/player?channel=7.1&title=PBS',
				POPOUT_WINDOW_TARGET,
				POPOUT_WINDOW_FEATURES,
			);
		});
	});
});
