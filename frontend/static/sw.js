// Minimal service worker: installability only, no caching whatsoever.
//
// If this is ever extended to cache anything, it must NEVER intercept or
// cache these endpoints - they're live streams/large media and stale or
// cached responses would break playback:
//   /api/streaming/*
//   /api/hls/*
//   /api/dvr/recording-stream*
//   /api/dvr/recording-detail
//   /api/dvr/recording-captions.vtt
//   /api/dvr/recording-thumbnails/*

self.addEventListener('install', () => {
	self.skipWaiting();
});

self.addEventListener('activate', (event) => {
	event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
	event.respondWith(fetch(event.request));
});
