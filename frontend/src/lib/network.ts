// Detects when the current page is served over an insecure origin (plain
// HTTP to a private/internal IP) where Chrome blocks microphone access
// unless the origin is manually added at
// chrome://flags/#unsafely-treat-insecure-origin-as-secure.

const PRIVATE_IPV4_PATTERN =
	/^(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})$/;

export function isPrivateIpHostname(hostname: string): boolean {
	return PRIVATE_IPV4_PATTERN.test(hostname);
}

export function isChromeBrowser(): boolean {
	if (typeof navigator === 'undefined') return false;
	const ua = navigator.userAgent;
	return /Chrome\//.test(ua) && !/Edg\//.test(ua) && !/OPR\//.test(ua);
}

export interface InsecureOriginInfo {
	needsInsecureOriginFlag: boolean;
	isChrome: boolean;
	origin: string;
}

export function getInsecureOriginInfo(): InsecureOriginInfo | null {
	if (typeof window === 'undefined') return null;
	const { protocol, hostname, origin } = window.location;
	return {
		needsInsecureOriginFlag: protocol === 'http:' && isPrivateIpHostname(hostname),
		isChrome: isChromeBrowser(),
		origin,
	};
}
