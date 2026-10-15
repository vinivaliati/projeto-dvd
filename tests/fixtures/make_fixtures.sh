#!/bin/sh
# Regenerate the ffprobe JSON fixtures from short lavfi clips. Run inside the Docker image,
# which has the pinned ffmpeg:
#   make fixtures
# The clips are temporary; only the JSON files are committed.
#
# Hand-written fixture (Debian's ffmpeg has no encoder for these, so it cannot be generated):
#   dv5_pgs.json: Dolby Vision profile 5 video, TrueHD 7.1 audio and a PGS subtitle, following
#   the layout of ffprobe 7.1 output for such a file.
set -eu

out="$(realpath "${1:?usage: make_fixtures.sh OUTPUT_DIR}")"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"

ff() { ffmpeg -nostdin -v error -y "$@"; }

printf '1\n00:00:00,500 --> 00:00:02,000\nOla\n' > sub.srt
printf ';FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=2000\ntitle=Um\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=2000\nEND=4000\ntitle=Dois\n' > chapters.txt
ff -f lavfi -i testsrc=s=300x450 -frames:v 1 cover.jpg

# Scope movie: two audio tracks with languages, a forced text subtitle, chapters, cover art.
ff -f lavfi -i testsrc=s=1920x800:r=24000/1001:d=4 \
   -f lavfi -i sine=d=4:sample_rate=48000 -f lavfi -i sine=f=600:d=4:sample_rate=48000 \
   -i sub.srt -i chapters.txt \
   -map 0:v -map 1:a -map 2:a -map 3 -map_chapters 4 \
   -c:v libx264 -preset ultrafast -c:a:0 ac3 -ac:a:0 6 -c:a:1 aac -ac:a:1 2 -c:s srt \
   -metadata:s:a:0 language=por -metadata:s:a:1 language=eng -metadata:s:a:1 title=Comentario \
   -metadata:s:s:0 language=por \
   -disposition:a:0 0 -disposition:a:1 0 -disposition:s:0 forced \
   -attach cover.jpg -metadata:s:t mimetype=image/jpeg -metadata:s:t filename=cover.jpg \
   movie.mkv

# Cover art stored as a video stream (attached_pic) after the real video.
ff -f lavfi -i testsrc=s=1280x720:r=25:d=2 -f lavfi -i sine=d=2 -i cover.jpg \
   -map 0 -map 1 -map 2 -c:v:0 libx264 -preset ultrafast -c:v:1 mjpeg \
   -disposition:v:1 attached_pic -c:a aac cover.mp4

# Audio with cover art only: no real video track.
ff -f lavfi -i sine=d=2 -i cover.jpg -map 0 -map 1 -c:a aac -c:v mjpeg \
   -disposition:v:0 attached_pic cover_only.mp4

# HDR10 in 4K (above 1080p).
ff -f lavfi -i testsrc=s=3840x2160:r=24:d=1 -c:v libx265 -preset ultrafast -pix_fmt yuv420p10le \
   -x265-params log-level=error:colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc \
   hdr10.mkv

# HLG.
ff -f lavfi -i testsrc=s=1920x1080:r=24:d=1 -c:v libx265 -preset ultrafast -pix_fmt yuv420p10le \
   -x265-params log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc \
   hlg.mp4

# NTSC DVD-style MPEG-2: anamorphic 16:9, 29.97 fps, stereo AC-3 without a language tag, and a
# real dvd_subtitle (bitmap) muxed by spumux; ffmpeg cannot encode bitmap subtitles from text.
ff -f lavfi -i "color=c=black@0.0:s=720x480,format=rgba,drawbox=x=100:y=400:w=200:h=30:color=white:t=fill" \
   -frames:v 1 sub.png
ff -f lavfi -i testsrc=s=720x480:r=30000/1001:d=2 -f lavfi -i sine=d=2:sample_rate=48000 \
   -c:v mpeg2video -aspect 16:9 -c:a ac3 -ac 2 -f dvd plain.mpg
printf '<subpictures><stream><spu start="00:00:00.50" end="00:00:01.50" image="sub.png"/></stream></subpictures>\n' > sub.xml
spumux -s0 sub.xml < plain.mpg > dvd.mpg 2> spumux.log

for clip in movie.mkv cover.mp4 cover_only.mp4 hdr10.mkv hlg.mp4 dvd.mpg; do
    ffprobe -v error -print_format json -show_format -show_streams -show_chapters "$clip" \
        > "$out/${clip%.*}.json"
done
