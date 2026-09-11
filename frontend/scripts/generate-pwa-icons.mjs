#!/usr/bin/env node
// One-off generator for PWA icon PNGs, rasterized from the existing
// favicon.svg mark. Run with `node scripts/generate-pwa-icons.mjs` after
// changing the source mark; the output PNGs are committed, not built.
import { readFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import sharp from 'sharp';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const faviconPath = path.join(root, 'src/lib/assets/favicon.svg');
const outDir = path.join(root, 'static/icons');

const BG = '#14161a';
const VIEWBOX_SIZE = 128;

const faviconSvg = readFileSync(faviconPath, 'utf8');
const inner = faviconSvg.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');

function wrapperSvg({ scale = 1 } = {}) {
	const translate = ((1 - scale) * VIEWBOX_SIZE) / 2;
	return `<svg xmlns="http://www.w3.org/2000/svg" width="${VIEWBOX_SIZE}" height="${VIEWBOX_SIZE}" viewBox="0 0 ${VIEWBOX_SIZE} ${VIEWBOX_SIZE}">` +
		`<rect width="${VIEWBOX_SIZE}" height="${VIEWBOX_SIZE}" fill="${BG}"/>` +
		`<g transform="translate(${translate} ${translate}) scale(${scale})">${inner}</g>` +
		`</svg>`;
}

async function render(svg, size, outPath, { flatten = false } = {}) {
	let img = sharp(Buffer.from(svg)).resize(size, size);
	// iOS renders a transparent apple-touch-icon as black, so that one must
	// be flattened to a fully opaque PNG (no alpha channel at all).
	if (flatten) img = img.flatten({ background: BG });
	await img.png().toFile(outPath);
	console.log(`wrote ${path.relative(root, outPath)}`);
}

mkdirSync(outDir, { recursive: true });

const fullBleed = wrapperSvg({ scale: 1 });
// Maskable icons get cropped to a circle/rounded-square by the OS; keep
// content inside a centered ~66%-scale safe zone so nothing gets clipped.
const maskable = wrapperSvg({ scale: 0.66 });

await render(fullBleed, 192, path.join(outDir, 'icon-192.png'));
await render(fullBleed, 512, path.join(outDir, 'icon-512.png'));
await render(maskable, 512, path.join(outDir, 'icon-512-maskable.png'));
await render(fullBleed, 180, path.join(outDir, 'apple-touch-icon-180.png'), { flatten: true });
