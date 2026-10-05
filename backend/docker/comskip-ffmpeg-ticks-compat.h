#ifndef COMSKIP_FFMPEG_TICKS_COMPAT_H
#define COMSKIP_FFMPEG_TICKS_COMPAT_H

/* AVCodecContext.ticks_per_frame was removed from newer ffmpeg releases
 * (the AV_CODEC_PROP_FIELDS flag used as its replacement below didn't exist
 * before then either, so its presence doubles as the version check); comskip
 * 0.83 was written against the older API that still had the field. Where
 * it's gone, the documented replacement is 2 for field-coded codecs
 * (MPEG-2, H.264) and 1 otherwise - see
 * https://github.com/erikkaashoek/Comskip/issues (ffmpeg 7/8 build reports).
 * mpeg2dec.c's direct reads of is->dec_ctx->ticks_per_frame are rewritten to
 * COMSKIP_TICKS(is->dec_ctx) at build time (see the comskip-builder stage in
 * Dockerfile) rather than patched per ffmpeg version. */
#ifdef AV_CODEC_PROP_FIELDS
#define COMSKIP_TICKS(c) (((c)->codec_descriptor && ((c)->codec_descriptor->props & AV_CODEC_PROP_FIELDS)) ? 2 : 1)
#else
#define COMSKIP_TICKS(c) ((c)->ticks_per_frame)
#endif

#endif
