const isDev = import.meta.env.DEV;

function log(level: 'debug' | 'info' | 'warn' | 'error', args: unknown[]) {
	if (!isDev && (level === 'debug' || level === 'info')) return;
	console[level](...args);
}

export const logger = {
	debug: (...args: unknown[]) => log('debug', args),
	info: (...args: unknown[]) => log('info', args),
	warn: (...args: unknown[]) => log('warn', args),
	error: (...args: unknown[]) => log('error', args),
};
