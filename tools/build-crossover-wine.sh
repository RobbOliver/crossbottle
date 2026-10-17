#!/bin/bash
# Build CodeWeavers' open-source (LGPL) CrossOver Wine for macOS x86_64 and add DXMT.
#
# Why: its mac driver exports `macdrv_functions`, which DXMT (Direct3D 10/11 -> Metal)
# needs, and its mac driver patches make Steam's interface much lighter than stock Wine.
#
# Needs: macOS on Apple Silicon or Intel, Xcode Command Line Tools, Homebrew, and a prior
# ./install.sh run (its Gcenx Wine provides the x86_64 FreeType/GnuTLS/MoltenVK dylibs).
# Takes about an hour on an M1. Result: <data dir>/Wine/CrossOver-Wine-<version>.
#
#   tools/build-crossover-wine.sh            # default 26.3.0
#   CX_VERSION=26.2.0 tools/build-crossover-wine.sh
set -euo pipefail

CX_VERSION="${CX_VERSION:-26.3.0}"
CX_URL="https://media.codeweavers.com/pub/crossover/source/crossover-sources-${CX_VERSION}.tar.gz"
DXMT_TAG="${DXMT_TAG:-v0.80}"
DXMT_URL="https://github.com/3Shain/dxmt/releases/download/${DXMT_TAG}/dxmt-${DXMT_TAG}-builtin.tar.gz"

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

SUPPORT="$HOME/Library/Application Support"
DATA="$SUPPORT/CrossBottle"
if [ -d "$SUPPORT/OpenBottle" ] && [ ! -e "$DATA" ]; then DATA="$SUPPORT/OpenBottle"; fi
GCENX_LIB="$(ls -d "$DATA"/Wine/*.app/Contents/Resources/wine/lib 2>/dev/null | head -1)"
[ -n "$GCENX_LIB" ] || die "run ./install.sh first (its Wine provides the x86_64 runtime libraries)"
command -v brew >/dev/null || die "Homebrew is required: https://brew.sh"

BUILD="$HOME/Library/Caches/CrossBottle/build-cx-$CX_VERSION"   # no spaces: Wine's build dislikes them
DEST="$DATA/Wine/CrossOver-Wine-${CX_VERSION%.0}"
mkdir -p "$BUILD"

say "Installing build tools (bison, mingw-w64, freetype and gnutls headers)"
brew install --quiet bison mingw-w64 freetype gnutls >/dev/null

say "Downloading CrossOver ${CX_VERSION} sources (~150 MB)"
[ -f "$BUILD/sources.tar.gz" ] || curl -fL --progress-bar -A 'Mozilla/5.0' -o "$BUILD/sources.tar.gz" "$CX_URL"
[ -d "$BUILD/sources/wine" ] || tar -xzf "$BUILD/sources.tar.gz" -C "$BUILD" sources/wine

# x86_64 runtime libraries, linked through a space-free path
ln -sfn "$GCENX_LIB" "$BUILD/xlib"
mkdir -p "$BUILD/inc" "$BUILD/wine-build"
ln -sfn "$(brew --prefix)/include/gnutls" "$BUILD/inc/gnutls"
# Build tools (sfnt2fon) load libfreetype by leaf name from the current directory.
for f in "$BUILD"/xlib/*.dylib; do ln -sf "$f" "$BUILD/wine-build/$(basename "$f")"; done

export PATH="$(brew --prefix)/opt/bison/bin:$(brew --prefix)/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PKG_CONFIG_LIBDIR=/nonexistent   # keep Homebrew's arm64 libraries out of an x86_64 build

say "Configuring (x86_64 under Rosetta, 32-bit support for Steam)"
cd "$BUILD/wine-build"
arch -x86_64 /bin/bash "$BUILD/sources/wine/configure" \
  --prefix="$BUILD/install" --enable-archs=i386,x86_64 --disable-tests \
  --without-x --without-gstreamer --without-sdl --without-cups --without-sane --without-pcap \
  --without-krb5 --without-gphoto --without-netapi --without-v4l2 --without-usb --without-pulse \
  --without-oss --with-freetype --with-gnutls \
  CC="clang -arch x86_64" OBJC="clang -arch x86_64" \
  CFLAGS="-O2 -g0 -mmacosx-version-min=10.15" OBJCFLAGS="-O2 -g0 -mmacosx-version-min=10.15" \
  LDFLAGS="-mmacosx-version-min=10.15 -Wl,-rpath,@loader_path/ -Wl,-rpath,@loader_path/../../" \
  ac_cv_lib_soname_freetype=libfreetype.6.dylib ac_cv_lib_soname_gnutls=libgnutls.30.dylib \
  ac_cv_lib_soname_vulkan=libvulkan.1.dylib \
  FREETYPE_CFLAGS="-I$(brew --prefix)/include/freetype2" FREETYPE_LIBS="-L$BUILD/xlib -lfreetype" \
  GNUTLS_CFLAGS="-I$BUILD/inc" GNUTLS_LIBS="-L$BUILD/xlib -lgnutls" > "$BUILD/configure.log"

say "Compiling Wine (about an hour; log: $BUILD/make.log)"
arch -x86_64 make -j"$(sysctl -n hw.ncpu)" > "$BUILD/make.log" 2>&1 || die "build failed, see $BUILD/make.log"
arch -x86_64 make install > "$BUILD/install.log" 2>&1

nm -gU "$BUILD/install/lib/wine/x86_64-unix/winemac.so" | grep -q macdrv_functions \
  || die "winemac.so does not export macdrv_functions; DXMT would not work"

say "Adding runtime libraries and Vulkan ICD"
cp -a "$BUILD"/xlib/*.dylib "$BUILD/install/lib/"
cp -a "$GCENX_LIB/wine/x86_64-unix/vulkan" "$BUILD/install/lib/wine/x86_64-unix/" 2>/dev/null || true

say "Adding DXMT ${DXMT_TAG} as builtin DLLs"
curl -fsSL -o "$BUILD/dxmt.tar.gz" "$DXMT_URL"
rm -rf "$BUILD/dxmt" && mkdir -p "$BUILD/dxmt" && tar -xzf "$BUILD/dxmt.tar.gz" -C "$BUILD/dxmt"
D="$(ls -d "$BUILD"/dxmt/*/ | head -1)"
cp "$D/x86_64-unix/winemetal.so" "$BUILD/install/lib/wine/x86_64-unix/"
cp "$D"/x86_64-windows/*.dll "$BUILD/install/lib/wine/x86_64-windows/"
cp "$D"/i386-windows/*.dll "$BUILD/install/lib/wine/i386-windows/"

say "Installing to $DEST"
rm -rf "$DEST" && mkdir -p "$DEST" && cp -a "$BUILD/install/." "$DEST/" && rm -rf "$DEST/include"
"$DEST/bin/wine" --version
cat <<EOF

Done. Use it for a bottle and switch Direct3D 10/11 to DXMT:
  crossbottle config Steam --wine "$DEST/bin/wine"
  crossbottle graphics Steam dxmt
  crossbottle shortcut --replace Steam 'C:\\Program Files (x86)\\Steam\\Steam.exe' --app-name Steam
EOF
