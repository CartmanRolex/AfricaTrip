package com.expedition.afrique;

import android.content.ContentResolver;
import android.content.Intent;
import android.media.MediaMetadataRetriever;
import android.net.Uri;
import android.os.Build;
import android.provider.MediaStore;
import android.util.Base64;

import androidx.activity.result.ActivityResult;
import androidx.exifinterface.media.ExifInterface;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.ActivityCallback;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Choix de PHOTOS ET VIDÉOS EN GARDANT leur localisation. C'est LE plugin qui
 * résout le problème de fond : sur Android, seule une app avec la permission
 * ACCESS_MEDIA_LOCATION peut lire la localisation NON expurgée d'un média
 * (via MediaStore.setRequireOriginal).
 *
 * Deux formes d'item renvoyées à JS :
 *   - photo : { base64, lat, lng, date, capturedAt } (GPS/date EXIF)
 *   - vidéo : { path, video:true, lat, lng, date, capturedAt } (GPS = atome ISO-6709
 *             QuickTime, MediaMetadataRetriever ; le FICHIER n'est PAS mis en
 *             base64 — trop lourd — mais copié en cache, `path` = file:// à
 *             relire côté JS via Capacitor.convertFileSrc puis uploader).
 */
@CapacitorPlugin(
    name = "AfricaMedia",
    permissions = {
        @Permission(alias = "media", strings = {
            "android.permission.ACCESS_MEDIA_LOCATION",
            "android.permission.READ_MEDIA_IMAGES",
            "android.permission.READ_MEDIA_VIDEO"
        })
    }
)
public class AfricaMediaPlugin extends Plugin {

    // ISO-6709 : "+DD.dddd-DDD.dddd/" (lat puis lng, altitude optionnelle après)
    private static final Pattern ISO6709 =
        Pattern.compile("([+-]\\d+(?:\\.\\d+)?)([+-]\\d+(?:\\.\\d+)?)");
    private static final Pattern EXIF_CAPTURED = Pattern.compile(
        "^(\\d{4}):(\\d{2}):(\\d{2})[ T](\\d{2}):(\\d{2}):(\\d{2})");
    private static final Pattern VIDEO_CAPTURED = Pattern.compile(
        "^(\\d{4})(\\d{2})(\\d{2})[T ](\\d{2})(\\d{2})(\\d{2})(?:\\.(\\d+))?(Z|[+-]\\d{2}:?\\d{2})?.*$");

    @PluginMethod
    public void pickWithLocation(PluginCall call) {
        if (getPermissionState("media") != PermissionState.GRANTED) {
            requestPermissionForAlias("media", call, "afterPerm");
        } else {
            launchPicker(call);
        }
    }

    @PermissionCallback
    private void afterPerm(PluginCall call) {
        launchPicker(call);   // on continue même si refusée : média sans GPS
    }

    private void launchPicker(PluginCall call) {
        Intent i = new Intent(Intent.ACTION_GET_CONTENT);
        i.setType("*/*");
        i.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"image/*", "video/*"});
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        startActivityForResult(call, Intent.createChooser(i, "Choisir photos / vidéos"), "picked");
    }

    @ActivityCallback
    private void picked(PluginCall call, ActivityResult result) {
        if (call == null) return;
        final List<Uri> uris = new ArrayList<>();
        Intent data = result.getData();
        if (data != null) {
            if (data.getClipData() != null) {
                for (int k = 0; k < data.getClipData().getItemCount(); k++)
                    uris.add(data.getClipData().getItemAt(k).getUri());
            } else if (data.getData() != null) {
                uris.add(data.getData());
            }
        }
        // Ce callback arrive sur le thread principal, et l'allègement d'une
        // vidéo dure des secondes : y rester ferait tuer l'app pour ANR.
        new Thread(() -> {
            JSArray items = new JSArray();
            for (Uri uri : uris) {
                try { items.put(readOne(uri)); } catch (Exception ignore) {}
            }
            JSObject ret = new JSObject();
            ret.put("items", items);
            call.resolve(ret);
        }, "africa-media").start();
    }

    private JSObject readOne(Uri uri) throws Exception {
        ContentResolver cr = getContext().getContentResolver();
        String mime = cr.getType(uri);
        boolean isVideo = mime != null && mime.startsWith("video/");

        // demande l'ORIGINAL non expurgé (nécessite ACCESS_MEDIA_LOCATION) ;
        // si l'URI ne le supporte pas, on lit tel quel (GPS possiblement absent)
        Uri readUri = uri;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try { readUri = MediaStore.setRequireOriginal(uri); } catch (Exception ignore) {}
        }

        return isVideo ? readVideo(cr, readUri, mime) : readImage(cr, readUri);
    }

    // ---- photo : base64 + GPS EXIF (comportement historique) ----------------
    private JSObject readImage(ContentResolver cr, Uri readUri) throws Exception {
        byte[] bytes;
        try (InputStream is = cr.openInputStream(readUri)) { bytes = readAll(is); }

        Double lat = null, lng = null; String date = null, capturedAt = null;
        try (InputStream es = cr.openInputStream(readUri)) {
            ExifInterface exif = new ExifInterface(es);
            double[] ll = exif.getLatLong();
            // getLatLong() ne rend PAS null quand les balises GPS sont vides :
            // beaucoup d'appareils ecrivent 0/1,0/1 et on recoit {0,0}. Ce
            // n'est pas un lieu, c'est l'absence de releve.
            if (ll != null && !(ll[0] == 0 && ll[1] == 0)) { lat = ll[0]; lng = ll[1]; }
            String dt = exif.getAttribute(ExifInterface.TAG_DATETIME_ORIGINAL);
            capturedAt = exifCapturedAt(exif, dt);
            if (capturedAt != null) date = capturedAt.substring(0, 10);
            else if (dt != null && dt.length() >= 10)
                date = dt.substring(0, 10).replace(":", "-");
        } catch (Exception ignore) {}

        JSObject o = new JSObject();
        o.put("base64", Base64.encodeToString(bytes, Base64.NO_WRAP));
        if (lat != null) { o.put("lat", lat); o.put("lng", lng); }
        if (date != null) o.put("date", date);
        if (capturedAt != null) o.put("capturedAt", capturedAt);
        return o;
    }

    // ---- vidéo : copie en cache (pas de base64) + GPS ISO-6709 + date -------
    private JSObject readVideo(ContentResolver cr, Uri readUri, String mime) throws Exception {
        // copie du flux vers un fichier de cache relisible par la WebView
        File out = File.createTempFile("clip", extFor(mime), getContext().getCacheDir());
        try (InputStream is = cr.openInputStream(readUri);
             FileOutputStream fos = new FileOutputStream(out)) {
            byte[] buf = new byte[65536]; int n;
            while ((n = is.read(buf)) != -1) fos.write(buf, 0, n);
        }

        // Allègement AVANT l'envoi : seul le débit baisse, la résolution est
        // conservée. Renvoie null quand il ne faut rien changer (clip déjà
        // léger, gain insuffisant, codec exotique) -> on garde l'original.
        File light = VideoTranscoder.lighten(out);
        if (light != null) {
            out.delete();
            out = light;
        }

        Double lat = null, lng = null; String date = null, capturedAt = null;
        MediaMetadataRetriever mmr = new MediaMetadataRetriever();
        try {
            mmr.setDataSource(getContext(), readUri);
            String loc = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_LOCATION);
            if (loc != null) {
                Matcher m = ISO6709.matcher(loc);
                if (m.find()) {
                    double la = Double.parseDouble(m.group(1)), ln = Double.parseDouble(m.group(2));
                    // Meme garde que pour les photos : +00.0000+000.0000 est un
                    // remplissage, pas une position.
                    if (!(la == 0 && ln == 0)) { lat = la; lng = ln; }
                }
            }
            String dt = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DATE);
            capturedAt = videoCapturedAt(dt);
            if (capturedAt != null) date = capturedAt.substring(0, 10);
            else if (dt != null && dt.length() >= 8 && dt.substring(0, 4).compareTo("2000") >= 0)
                date = dt.substring(0, 4) + "-" + dt.substring(4, 6) + "-" + dt.substring(6, 8);
        } catch (Exception ignore) {
        } finally {
            try { mmr.release(); } catch (Exception ignore) {}
        }

        JSObject o = new JSObject();
        o.put("path", "file://" + out.getAbsolutePath());
        o.put("video", true);
        // Taille du fichier copie : la WebView doit le charger entierement en
        // memoire pour l'envoyer, donc le JS a besoin de la connaitre AVANT
        // d'essayer, pour refuser proprement au lieu d'echouer sur un fetch.
        o.put("bytes", out.length());
        if (lat != null) { o.put("lat", lat); o.put("lng", lng); }
        if (date != null) o.put("date", date);
        if (capturedAt != null) o.put("capturedAt", capturedAt);
        return o;
    }

    private static String exifCapturedAt(ExifInterface exif, String raw) {
        if (raw == null) return null;
        Matcher m = EXIF_CAPTURED.matcher(raw);
        if (!m.find()) return null;
        String iso = m.group(1) + "-" + m.group(2) + "-" + m.group(3)
            + "T" + m.group(4) + ":" + m.group(5) + ":" + m.group(6);
        String offset = exif.getAttribute(ExifInterface.TAG_OFFSET_TIME_ORIGINAL);
        if (offset != null && offset.matches("[+-]\\d{2}:?\\d{2}")) {
            if (offset.length() == 5) offset = offset.substring(0, 3) + ":" + offset.substring(3);
            iso += offset;
        }
        return iso;
    }

    private static String videoCapturedAt(String raw) {
        if (raw == null) return null;
        Matcher m = VIDEO_CAPTURED.matcher(raw.trim());
        if (!m.matches() || m.group(1).compareTo("2000") < 0) return null;
        String iso = m.group(1) + "-" + m.group(2) + "-" + m.group(3)
            + "T" + m.group(4) + ":" + m.group(5) + ":" + m.group(6);
        if (m.group(7) != null) iso += "." + m.group(7).substring(0, Math.min(3, m.group(7).length()));
        String offset = m.group(8);
        if (offset != null) {
            if (offset.matches("[+-]\\d{4}")) offset = offset.substring(0, 3) + ":" + offset.substring(3);
            iso += offset;
        }
        return iso;
    }

    private static String extFor(String mime) {
        if (mime == null) return ".mp4";
        if (mime.contains("quicktime")) return ".mov";
        if (mime.contains("webm")) return ".webm";
        if (mime.contains("3gpp")) return ".3gp";
        if (mime.contains("matroska")) return ".mkv";
        return ".mp4";
    }

    private static byte[] readAll(InputStream is) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = is.read(buf)) != -1) out.write(buf, 0, n);
        return out.toByteArray();
    }
}
