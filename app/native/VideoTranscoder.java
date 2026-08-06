package com.expedition.afrique;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMetadataRetriever;
import android.media.MediaMuxer;
import android.view.Surface;

import java.io.File;
import java.nio.ByteBuffer;

/**
 * Allège une vidéo AVANT son envoi, en ne touchant QU'AU DÉBIT.
 *
 * La résolution, la durée et la cadence sont conservées à l'identique : un
 * téléphone filme à un débit très supérieur à ce que l'image exige (~50 Mb/s en
 * 4K, ~17 Mb/s en 1080p), et c'est ce seul excès qu'on retire. Rien n'est
 * redimensionné, aucune image n'est jetée.
 *
 * C'est le trajet téléphone -> Cloudinary qu'on raccourcit : en données mobiles
 * et sur un réseau instable, un clip de 150 Mo est le vrai point de rupture des
 * envois. Les transformations Cloudinary (`q_auto,w_1280,c_limit`) sont un sujet
 * distinct : elles allègent ce que le VISITEUR télécharge, une fois le fichier
 * déjà stocké.
 *
 * Trois garde-fous, parce qu'un ré-encodage est une perte définitive :
 *   - en dessous de {@link #MIN_BYTES}, on ne touche à rien ;
 *   - si le gain attendu n'est pas franc ({@link #WORTH_IT}), on renonce ;
 *   - toute erreur (codec exotique, mémoire, format illisible) renvoie null, et
 *     l'appelant envoie l'original.
 *
 * L'image passe du décodeur à l'encodeur par une Surface : les pixels ne
 * transitent jamais par la mémoire Java, ce qui rend l'opération tenable sur un
 * téléphone modeste, même en 4K.
 */
final class VideoTranscoder {

    /** En dessous, la vidéo est déjà raisonnable : on la laisse strictement intacte. */
    static final long MIN_BYTES = 25L * 1024 * 1024;
    /**
     * Qualité visée, en bits par pixel et par image. 0.11 est le haut du panier
     * pour du H.264 (~6,8 Mb/s en 1080p30) : on reste très loin d'une
     * compression agressive, l'objectif est le poids, pas l'économie.
     */
    private static final double TARGET_BPP = 0.11;
    private static final int MAX_BITRATE = 16_000_000;
    private static final int MIN_BITRATE = 2_000_000;
    /** Ré-encoder sans gagner au moins 25 % perdrait de la qualité pour rien. */
    private static final double WORTH_IT = 0.75;
    private static final int TIMEOUT_US = 10_000;

    private VideoTranscoder() {}

    /**
     * @return le fichier allégé, ou null s'il ne faut rien changer (vidéo déjà
     *         légère, gain insuffisant, ou échec — dans tous ces cas l'appelant
     *         garde l'original).
     */
    static File lighten(File input) {
        if (input == null || input.length() < MIN_BYTES) return null;

        MediaExtractor extractor = null;
        MediaCodec decoder = null, encoder = null;
        MediaMuxer muxer = null;
        Surface surface = null;
        File output = null;
        boolean muxerStarted = false, ok = false;

        try {
            extractor = new MediaExtractor();
            extractor.setDataSource(input.getAbsolutePath());

            int videoTrack = -1, audioTrack = -1;
            MediaFormat videoFormat = null, audioFormat = null;
            for (int i = 0; i < extractor.getTrackCount(); i++) {
                MediaFormat f = extractor.getTrackFormat(i);
                String mime = f.getString(MediaFormat.KEY_MIME);
                if (mime == null) continue;
                if (mime.startsWith("video/") && videoTrack < 0) { videoTrack = i; videoFormat = f; }
                else if (mime.startsWith("audio/") && audioTrack < 0) { audioTrack = i; audioFormat = f; }
            }
            if (videoTrack < 0) return null;

            final int width = intOr(videoFormat, MediaFormat.KEY_WIDTH, 0);
            final int height = intOr(videoFormat, MediaFormat.KEY_HEIGHT, 0);
            if (width <= 0 || height <= 0) return null;
            final int fps = clamp(intOr(videoFormat, MediaFormat.KEY_FRAME_RATE, 30), 1, 240);

            // Le débit source se déduit du poids réel : KEY_BIT_RATE est le plus
            // souvent absent des pistes rendues par MediaExtractor.
            double seconds = longOr(videoFormat, MediaFormat.KEY_DURATION, 0L) / 1_000_000d;
            if (seconds <= 0) return null;
            long sourceBitrate = (long) (input.length() * 8 / seconds);

            int target = (int) Math.round(TARGET_BPP * width * height * fps);
            target = clamp(target, MIN_BITRATE, MAX_BITRATE);
            if (target > sourceBitrate * WORTH_IT) return null;   // gain trop maigre

            // La rotation est une métadonnée : les images décodées ne sont jamais
            // tournées. Sans la reporter sur le conteneur, un clip filmé en
            // portrait ressortirait couché.
            int rotation = rotationOf(input);

            output = File.createTempFile("light", ".mp4", input.getParentFile());
            muxer = new MediaMuxer(output.getAbsolutePath(), MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            if (rotation != 0) muxer.setOrientationHint(rotation);

            MediaFormat outFormat = MediaFormat.createVideoFormat("video/avc", width, height);
            outFormat.setInteger(MediaFormat.KEY_COLOR_FORMAT,
                MediaCodecInfo.CodecCapabilities.COLOR_FormatSurface);
            outFormat.setInteger(MediaFormat.KEY_BIT_RATE, target);
            outFormat.setInteger(MediaFormat.KEY_FRAME_RATE, fps);
            outFormat.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 2);
            outFormat.setInteger(MediaFormat.KEY_BITRATE_MODE,
                MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_VBR);

            encoder = MediaCodec.createEncoderByType("video/avc");
            encoder.configure(outFormat, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE);
            surface = encoder.createInputSurface();
            encoder.start();

            decoder = MediaCodec.createDecoderByType(videoFormat.getString(MediaFormat.KEY_MIME));
            decoder.configure(videoFormat, surface, null, 0);
            decoder.start();

            extractor.selectTrack(videoTrack);

            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            int outVideo = -1, outAudio = -1;
            boolean readDone = false, decodeDone = false, encodeDone = false;

            while (!encodeDone) {
                // 1. fichier -> décodeur
                if (!readDone) {
                    int in = decoder.dequeueInputBuffer(TIMEOUT_US);
                    if (in >= 0) {
                        ByteBuffer buf = decoder.getInputBuffer(in);
                        int n = buf == null ? -1 : extractor.readSampleData(buf, 0);
                        if (n < 0) {
                            decoder.queueInputBuffer(in, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                            readDone = true;
                        } else {
                            decoder.queueInputBuffer(in, 0, n, extractor.getSampleTime(), 0);
                            extractor.advance();
                        }
                    }
                }

                // 2. décodeur -> Surface de l'encodeur (aucune copie en RAM)
                if (!decodeDone) {
                    int out = decoder.dequeueOutputBuffer(info, TIMEOUT_US);
                    if (out >= 0) {
                        decoder.releaseOutputBuffer(out, info.size > 0);
                        if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) {
                            decodeDone = true;
                            encoder.signalEndOfInputStream();
                        }
                    }
                }

                // 3. encodeur -> fichier
                int out = encoder.dequeueOutputBuffer(info, TIMEOUT_US);
                if (out == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    // Les deux pistes doivent être déclarées avant start() ; le
                    // format vidéo définitif (csd) n'est connu qu'ici.
                    outVideo = muxer.addTrack(encoder.getOutputFormat());
                    if (audioFormat != null) outAudio = muxer.addTrack(audioFormat);
                    muxer.start();
                    muxerStarted = true;
                } else if (out >= 0) {
                    ByteBuffer buf = encoder.getOutputBuffer(out);
                    // le csd voyage déjà dans le format de piste : ne pas le réécrire
                    if ((info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) info.size = 0;
                    if (info.size > 0 && muxerStarted && buf != null) {
                        buf.position(info.offset);
                        buf.limit(info.offset + info.size);
                        muxer.writeSampleData(outVideo, buf, info);
                    }
                    encoder.releaseOutputBuffer(out, false);
                    if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) encodeDone = true;
                }
            }

            // 4. le son est recopié tel quel : il pèse peu, et le ré-encoder
            //    n'apporterait qu'une dégradation.
            if (outAudio >= 0 && muxerStarted) {
                MediaExtractor audio = new MediaExtractor();
                try {
                    audio.setDataSource(input.getAbsolutePath());
                    audio.selectTrack(audioTrack);
                    ByteBuffer buf = ByteBuffer.allocate(
                        Math.max(intOr(audioFormat, MediaFormat.KEY_MAX_INPUT_SIZE, 0), 256 * 1024));
                    MediaCodec.BufferInfo ai = new MediaCodec.BufferInfo();
                    while (true) {
                        int n = audio.readSampleData(buf, 0);
                        if (n < 0) break;
                        ai.offset = 0;
                        ai.size = n;
                        ai.presentationTimeUs = audio.getSampleTime();
                        ai.flags = audio.getSampleFlags();
                        muxer.writeSampleData(outAudio, buf, ai);
                        audio.advance();
                    }
                } finally {
                    try { audio.release(); } catch (Exception ignore) {}
                }
            }

            ok = muxerStarted;
        } catch (Throwable t) {
            ok = false;   // codec exotique, mémoire, fichier illisible -> original
        } finally {
            if (muxer != null) {
                try { if (muxerStarted) muxer.stop(); } catch (Exception ignore) { ok = false; }
                try { muxer.release(); } catch (Exception ignore) {}
            }
            release(decoder);
            release(encoder);
            if (surface != null) try { surface.release(); } catch (Exception ignore) {}
            if (extractor != null) try { extractor.release(); } catch (Exception ignore) {}
        }

        // Dernier filet : un ré-encodage qui n'allège pas est un ré-encodage
        // perdu. On ne garde le résultat que s'il est réellement plus léger.
        if (ok && output != null && output.length() > 0 && output.length() < input.length()) {
            return output;
        }
        if (output != null) output.delete();
        return null;
    }

    private static void release(MediaCodec codec) {
        if (codec == null) return;
        try { codec.stop(); } catch (Exception ignore) {}
        try { codec.release(); } catch (Exception ignore) {}
    }

    private static int rotationOf(File f) {
        MediaMetadataRetriever mmr = new MediaMetadataRetriever();
        try {
            mmr.setDataSource(f.getAbsolutePath());
            String r = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION);
            return r == null ? 0 : Integer.parseInt(r.trim());
        } catch (Exception ignore) {
            return 0;
        } finally {
            try { mmr.release(); } catch (Exception ignore) {}
        }
    }

    // MediaFormat lève si la clé manque, et la cadence est tantôt entière
    // tantôt flottante selon le conteneur.
    private static int intOr(MediaFormat f, String key, int fallback) {
        try { return f.getInteger(key); } catch (Exception ignore) {}
        try { return Math.round(f.getFloat(key)); } catch (Exception ignore) {}
        return fallback;
    }

    private static long longOr(MediaFormat f, String key, long fallback) {
        try { return f.getLong(key); } catch (Exception ignore) {}
        return fallback;
    }

    private static int clamp(int v, int lo, int hi) {
        return v < lo ? lo : (v > hi ? hi : v);
    }
}
