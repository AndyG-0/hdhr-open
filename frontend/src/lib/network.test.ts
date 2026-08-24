import { afterEach, describe, expect, it, vi } from 'vitest';
import { getInsecureOriginInfo, isChromeBrowser, isPrivateIpHostname } from './network';

describe('network', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
	});

	describe('isPrivateIpHostname', () => {
		it.each(['10.0.0.1', '10.255.255.255', '172.16.0.1', '172.31.255.255', '192.168.1.50', '192.168.0.1'])(
			'is true for private IPv4 address %s',
			(hostname) => {
				expect(isPrivateIpHostname(hostname)).toBe(true);
			},
		);

		it.each(['8.8.8.8', '172.15.0.1', '172.32.0.1', '11.0.0.1', '193.168.1.1', 'localhost', 'example.com', '::1'])(
			'is false for non-private-IPv4 host %s',
			(hostname) => {
				expect(isPrivateIpHostname(hostname)).toBe(false);
			},
		);
	});

	describe('isChromeBrowser', () => {
		it('is true for a Chrome user agent', () => {
			vi.stubGlobal('navigator', {
				userAgent:
					'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
			});
			expect(isChromeBrowser()).toBe(true);
		});

		it('is false for Edge, which also contains "Chrome" in its UA', () => {
			vi.stubGlobal('navigator', {
				userAgent:
					'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
			});
			expect(isChromeBrowser()).toBe(false);
		});

		it('is false for a non-Chrome user agent', () => {
			vi.stubGlobal('navigator', {
				userAgent:
					'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15) AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15',
			});
			expect(isChromeBrowser()).toBe(false);
		});
	});

	describe('getInsecureOriginInfo', () => {
		it('flags an http origin at a private IP as needing the flag', () => {
			vi.stubGlobal('window', {
				location: { protocol: 'http:', hostname: '192.168.1.50', origin: 'http://192.168.1.50:8080' },
			});
			vi.stubGlobal('navigator', { userAgent: 'Chrome/120.0.0.0' });

			expect(getInsecureOriginInfo()).toEqual({
				needsInsecureOriginFlag: true,
				isChrome: true,
				origin: 'http://192.168.1.50:8080',
			});
		});

		it('does not flag an https origin at a private IP', () => {
			vi.stubGlobal('window', {
				location: { protocol: 'https:', hostname: '192.168.1.50', origin: 'https://192.168.1.50' },
			});

			expect(getInsecureOriginInfo()?.needsInsecureOriginFlag).toBe(false);
		});

		it('does not flag an http origin at a public hostname', () => {
			vi.stubGlobal('window', {
				location: { protocol: 'http:', hostname: 'example.com', origin: 'http://example.com' },
			});

			expect(getInsecureOriginInfo()?.needsInsecureOriginFlag).toBe(false);
		});
	});
});
