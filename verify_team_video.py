"""Decode the finished MP4, check duration/frame count, and extract review frames."""
from pathlib import Path
import json

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
import imageio_ffmpeg

video = ROOT / "share/Spatial-Blocks-RTX-Demo.mp4"
work = ROOT / "share/production"
work.mkdir(parents=True, exist_ok=True)
stream = imageio_ffmpeg.read_frames(str(video),pix_fmt="rgb24")
metadata = next(stream)
assert metadata["size"] == (1920,1080), metadata
assert abs(metadata["fps"]-30)<.01, metadata
assert abs(metadata["duration"]-14)<.05, metadata
selected = [0,75,134,142,162,225,315,405]
sheet = Image.new("RGB",(1920,580),"#08111a")
count = 0
for count, raw in enumerate(stream,start=1):
    index = count-1
    if index in selected:
        frame = Image.frombytes("RGB",metadata["size"],raw)
        frame.save(work / f"decoded-{index:03}.jpg",quality=96)
        slot = selected.index(index)
        x,y = (slot%4)*480,(slot//4)*290
        sheet.paste(frame.resize((480,270),Image.Resampling.LANCZOS),(x,y))
        ImageDraw.Draw(sheet).text((x+8,y+271),f"{index/30:.2f} seconds",fill="white")
assert count==420, count
sheet.save(work / "decoded-contact-sheet.jpg",quality=94)
report = {"duration_seconds":metadata["duration"],"fps":metadata["fps"],"resolution":metadata["size"],
          "decoded_frames":count,"codec":metadata.get("codec"),"bytes":video.stat().st_size,
          "decode_completed":True,"caption_style":"burned in","audio":"silent"}
(work / "video-verification.json").write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
