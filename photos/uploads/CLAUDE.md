# photos/uploads/ — shared trip photos (map bubbles)

> Rule: update this file in the same commit as any feature change here.

Resized copies (max 1600 px JPEG) of the photos everyone uploads to the
shared Google Drive folder, downloaded by `python src/fetch_photos.py` —
**do not add or edit files by hand**. File names are the Drive file ids,
matching the `id`/`file` fields in `src/gallery.json`.

They are served by GitHub Pages at their relative path when a map bubble is
clicked (the lightbox); the bubbles themselves use 96 px thumbs embedded in
`gallery.json` as data URIs, so the standalone `voyage-afrique.html` still
shows bubbles (and falls back to the thumb in the lightbox) without this
folder.

To remove a photo: delete it in Drive AND remove its file here + its entry
in `src/gallery.json`, then rebuild.
