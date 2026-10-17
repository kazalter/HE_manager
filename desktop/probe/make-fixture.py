"""Create a public synthetic clip with two audio and two subtitle tracks."""
import hashlib
import json
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
out = root / "native/runtime/fixtures"
out.mkdir(parents=True, exist_ok=True)
for name, text in [("a.srt", "HE CP-01 subtitle A"), ("b.srt", "HE CP-01 subtitle B")]:
    (out / name).write_text("1\n00:00:00,000 --> 00:00:30,000\n" + text + "\n", encoding="utf-8")
target = out / "acceptance.mkv"
arguments = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-stream_loop", "-1", "-i", str(root / "resources/test/sample.mp4"), "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000", "-i", str(out / "a.srt"), "-i", str(out / "b.srt"), "-t", "30", "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:s", "-map", "4:s", "-vf", "drawbox=x=560:y=0:w=80:h=36:color=red:t=fill,drawbox=x=560:y=324:w=80:h=36:color=blue:t=fill", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-threads", "2", "-c:a", "aac", "-c:s", "srt", "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=jpn", "-metadata:s:s:0", "language=eng", "-metadata:s:s:1", "language=jpn", str(target)]
subprocess.run(arguments, check=True)
(out / "fixture-manifest.json").write_text(json.dumps({"description": "30s synthetic H.264 with two AAC tones and two SRT tracks", "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "bytes": target.stat().st_size, "arguments": arguments[1:]}, indent=2) + "\n")
print(target)
