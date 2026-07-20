package com.expedition.afrique;

import android.content.ContentResolver;
import android.content.Intent;
import android.net.Uri;
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
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

/**
 * Choix de photos EN GARDANT leur localisation. C'est LE plugin qui résout le
 * problème de fond : sur Android, seule une app avec la permission
 * ACCESS_MEDIA_LOCATION peut lire le GPS EXIF non expurgé d'une photo
 * (via MediaStore.setRequireOriginal). Renvoie à JS une liste
 * { base64, lat, lng, date } par photo choisie.
 */
@CapacitorPlugin(
    name = "AfricaMedia",
    permissions = {
        @Permission(alias = "media", strings = {
            "android.permission.ACCESS_MEDIA_LOCATION",
            "android.permission.READ_MEDIA_IMAGES"
        })
    }
)
public class AfricaMediaPlugin extends Plugin {

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
        launchPicker(call);   // on continue même si refusée : photo sans GPS
    }

    private void launchPicker(PluginCall call) {
        Intent i = new Intent(Intent.ACTION_GET_CONTENT);
        i.setType("image/*");
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        startActivityForResult(call, Intent.createChooser(i, "Choisir des photos"), "picked");
    }

    @ActivityCallback
    private void picked(PluginCall call, ActivityResult result) {
        if (call == null) return;
        JSArray items = new JSArray();
        Intent data = result.getData();
        if (data != null) {
            List<Uri> uris = new ArrayList<>();
            if (data.getClipData() != null) {
                for (int k = 0; k < data.getClipData().getItemCount(); k++)
                    uris.add(data.getClipData().getItemAt(k).getUri());
            } else if (data.getData() != null) {
                uris.add(data.getData());
            }
            for (Uri uri : uris) {
                try { items.put(readOne(uri)); } catch (Exception ignore) {}
            }
        }
        JSObject ret = new JSObject();
        ret.put("items", items);
        call.resolve(ret);
    }

    private JSObject readOne(Uri uri) throws Exception {
        ContentResolver cr = getContext().getContentResolver();
        // demande l'ORIGINAL non expurgé (nécessite ACCESS_MEDIA_LOCATION) ;
        // si l'URI ne le supporte pas, on lit tel quel (GPS possiblement absent)
        Uri readUri = uri;
        try { readUri = MediaStore.setRequireOriginal(uri); } catch (Exception ignore) {}

        byte[] bytes;
        try (InputStream is = cr.openInputStream(readUri)) { bytes = readAll(is); }

        Double lat = null, lng = null; String date = null;
        try (InputStream es = cr.openInputStream(readUri)) {
            ExifInterface exif = new ExifInterface(es);
            double[] ll = exif.getLatLong();
            if (ll != null) { lat = ll[0]; lng = ll[1]; }
            String dt = exif.getAttribute(ExifInterface.TAG_DATETIME_ORIGINAL);
            if (dt != null && dt.length() >= 10)
                date = dt.substring(0, 10).replace(":", "-");
        } catch (Exception ignore) {}

        JSObject o = new JSObject();
        o.put("base64", Base64.encodeToString(bytes, Base64.NO_WRAP));
        if (lat != null) { o.put("lat", lat); o.put("lng", lng); }
        if (date != null) o.put("date", date);
        return o;
    }

    private static byte[] readAll(InputStream is) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = is.read(buf)) != -1) out.write(buf, 0, n);
        return out.toByteArray();
    }
}
