export interface PopoutPlayerOptions {
	channel?: string;
	recording?: string;
	playUrl?: string;
	title?: string;
	t?: number;
}

export const POPOUT_WINDOW_TARGET = 'hdhr_popout_player';
export const POPOUT_WINDOW_FEATURES =
	'width=960,height=540,menubar=no,toolbar=no,location=no,status=no,resizable=yes';

export function buildPopoutUrl(options: PopoutPlayerOptions): string {
	const params = new URLSearchParams();
	if (options.channel) params.set('channel', options.channel);
	if (options.recording) params.set('recording', options.recording);
	if (options.playUrl) params.set('play_url', options.playUrl);
	if (options.title) params.set('title', options.title);
	if (options.t !== undefined && options.t > 0) params.set('t', Math.floor(options.t).toString());
	return `/player?${params.toString()}`;
}

export function openPopoutPlayer(options: PopoutPlayerOptions): Window | null {
	if (typeof window === 'undefined') return null;
	const url = buildPopoutUrl(options);
	return window.open(url, POPOUT_WINDOW_TARGET, POPOUT_WINDOW_FEATURES);
}
