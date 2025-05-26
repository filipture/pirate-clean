#!/bin/bash

# Nazwa pliku wejściowego
ICON_SRC="pirate_reddit_logo.png"
ICON_NAME="icon.icns"
DEST="src-tauri/icons"

# Tworzenie katalogu tymczasowego
mkdir -p icon.iconset

# Generowanie różnych rozmiarów
sips -z 16 16     "$ICON_SRC" --out icon.iconset/icon_16x16.png
sips -z 32 32     "$ICON_SRC" --out icon.iconset/icon_16x16@2x.png
sips -z 32 32     "$ICON_SRC" --out icon.iconset/icon_32x32.png
sips -z 64 64     "$ICON_SRC" --out icon.iconset/icon_32x32@2x.png
sips -z 128 128   "$ICON_SRC" --out icon.iconset/icon_128x128.png
sips -z 256 256   "$ICON_SRC" --out icon.iconset/icon_128x128@2x.png
sips -z 256 256   "$ICON_SRC" --out icon.iconset/icon_256x256.png
sips -z 512 512   "$ICON_SRC" --out icon.iconset/icon_256x256@2x.png
sips -z 512 512   "$ICON_SRC" --out icon.iconset/icon_512x512.png
cp "$ICON_SRC" icon.iconset/icon_512x512@2x.png

# Konwersja do .icns
iconutil -c icns icon.iconset -o "$ICON_NAME"

# Przeniesienie do src-tauri/icons
mkdir -p "$DEST"
mv "$ICON_NAME" "$DEST"

# Sprzątanie
rm -r icon.iconset

echo "✅ Ikona gotowa: $DEST/$ICON_NAME"
