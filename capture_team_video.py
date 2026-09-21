"""Render a captioned, 14-second demonstration through the real game and RTX engine."""
from pathlib import Path
import json
import math
import subprocess
import threading

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
import imageio_ffmpeg
from game import Game, Piece
from renderer3d import RtxScene

OUT = ROOT / "share"
WORK = OUT / "production"
FPS, SECONDS = 30, 14
WIDTH, HEIGHT = 1920, 1080
FONT = Path("C:/Windows/Fonts")
WHITE, MUTED, MINT, CYAN = "#edf4f7", "#94a8b8", "#b4eeaa", "#64d4e3"


def font(size, bold=False):
    return ImageFont.truetype(str(FONT / ("segoeuib.ttf" if bold else "segoeui.ttf")), size)


FONTS = {size: font(size) for size in (18, 20, 22, 24, 26, 30, 34, 38, 44, 52, 62)}
BOLD = {size: font(size, True) for size in (22, 26, 30, 34, 38, 44, 52, 62)}


def text(draw, xy, value, size=26, fill=WHITE, bold=False, **kwargs):
    draw.text(xy, value, font=(BOLD if bold else FONTS)[size], fill=fill, **kwargs)


CHAPTERS = [
    (0., 4.4, "01  /  CHECK THE MOVE", "ovspatialquery", "Tests candidate placements", "Exact box-overlap queries power\nmovement, rotation and the landing guide.", "CPU / SPATIAL QUERIES"),
    (4.4, 7., "02  /  UPDATE THE WORLD", "ovstage", "A clear changes the scene", "Game rules remove completed rows.\nVersioned scene updates reach the renderer.", "RUNTIME SCENE DATA"),
    (7., 10.8, "03  /  RENDER THE RESULT", "ovrtx", "Light makes it tangible", "RTX shading, reflections and bloom\nbring the blocks and effects to life.", "GPU / RTX RENDERING"),
    (10.8, 14., "04  /  BRING IT TOGETHER", "One playable application", "Queries + scene + rendering", "Python coordinates the game.\nEach library has a focused responsibility.", "COMPOSABLE NATIVE LIBRARIES"),
]

EVENTS = {
    24: ["left"], 48: ["rotate"], 78: ["right"], 101: ["left"], 116: ["right"],
    135: ["drop"], 168: ["left"], 176: ["left"], 186: ["rotate"], 202: ["drop"],
    218: ["right"], 226: ["right"], 233: ["rotate"], 252: ["drop"],
    270: ["rotate"], 282: ["right"], 290: ["right"], 298: ["right"], 316: ["drop"],
    344: ["left"], 353: ["left"], 360: ["rotate"], 381: ["drop"],
}


def smooth(value):
    value = max(0., min(1., value))
    return value*value*(3-2*value)


class Composer:
    def __init__(self):
        y, x = np.mgrid[:HEIGHT, :WIDTH]
        glow = np.exp(-(((x-1000)/1100)**2 + ((y-170)/800)**2))
        base = np.array([7, 13, 19], dtype=np.float32)
        pixels = np.clip(base + glow[:,:,None]*[10, 17, 20], 0, 255).astype(np.uint8)
        self.background = Image.fromarray(pixels)
        self.mask = Image.new("L", (1092, 930), 0)
        ImageDraw.Draw(self.mask).rounded_rectangle((0,0,1091,929), radius=18, fill=255)

    def compose(self, pixels, state, scene, now, last_action):
        result = self.background.copy()
        draw = ImageDraw.Draw(result)
        # The 3D content is copied from the actual ovrtx LdrColor output.
        rendered = Image.fromarray(pixels).convert("RGB").resize((1034, 930), Image.Resampling.LANCZOS)
        viewport = Image.new("RGB", (1092, 930), "#101b24")
        viewport.paste(rendered, (29, 0))
        result.paste(viewport, (48, 100), self.mask)
        draw.rounded_rectangle((48,100,1140,1030), radius=18, outline="#334a58", width=2)
        text(draw, (49, 30), "SPATIAL BLOCKS", 38, bold=True)
        text(draw, (372, 44), "/   RTX EDITION", 22, fill=MINT)
        draw.ellipse((984,48,994,58), fill=MINT)
        text(draw, (1007, 38), "NATIVE 3D", 20, fill=MUTED)
        # Large, stable captions remain readable in a shared video player.
        chapter_index = next(i for i,c in enumerate(CHAPTERS) if c[0]<=now<c[1])
        _, _, number, name, headline, copy, tag = CHAPTERS[chapter_index]
        left = 1190
        text(draw, (left, 106), number, 22, fill=MINT)
        name_size = 52 if chapter_index<3 else 44
        text(draw, (left, 161), name, name_size, bold=True)
        text(draw, (left, 237), tag, 20, fill=CYAN)
        draw.line((left,282,1870,282), fill="#304653", width=2)
        text(draw, (left, 307), headline, 30, bold=True)
        draw.multiline_text((left, 359), copy, font=FONTS[26], fill=MUTED, spacing=13)

        # A persistent flow diagram ties all four editorial beats together.
        rows = [("ovspatialquery", "Can the piece fit?", 0), ("ovstage", "Publish scene changes", 1), ("ovrtx", "Render the 3D view", 2)]
        for i, (label, detail, target) in enumerate(rows):
            top = 493+i*91
            active = chapter_index==target or chapter_index==3
            draw.rounded_rectangle((left,top,1870,top+72), radius=11,
                                   fill="#1a3037" if active else "#111e28", outline="#608d8b" if active else "#283b49", width=2)
            draw.ellipse((left+19,top+30,left+29,top+40), fill=MINT if active else "#506673")
            text(draw, (left+44, top+12), label, 26, fill=WHITE if active else MUTED, bold=True)
            text(draw, (left+299, top+17), detail, 22, fill=MUTED)
            if i<2:
                draw.line((left+340,top+73,left+340,top+88), fill="#4d7282", width=2)
                draw.polygon([(left+335,top+83),(left+345,top+83),(left+340,top+89)], fill="#4d7282")

        draw.line((left,785,1870,785), fill="#304653", width=2)
        for xpos, label, value in [(left,"OVERLAP CHECKS",f"{state['engine']['queries']:,}"),
                                   (left+286,"LINES CLEARED",str(state['lines'])),
                                   (left+515,"SCORE",str(state['score']))]:
            text(draw, (xpos,811), label, 18, fill=MUTED)
            text(draw, (xpos,845), value, 38, bold=True)
        text(draw, (left,922), "Scripted gameplay · real native libraries", 22, fill=MUTED)
        text(draw, (left,958), "Prepared board · RTX A6000 · captioned demo", 20, fill="#718a9c")
        # Input labels make the cause of each visible action apparent.
        action_name, action_time = last_action
        if now-action_time < .75:
            label = {"left":"MOVE LEFT", "right":"MOVE RIGHT", "rotate":"ROTATE", "drop":"HARD DROP"}.get(action_name, "")
            if label:
                draw.rounded_rectangle((77,936,311,991), radius=9, fill="#10212bec", outline="#52798b", width=1)
                text(draw, (94,947), label, 26, fill=WHITE, bold=True)
        if 4.5<=now<5.8:
            draw.rounded_rectangle((398,520,807,607), radius=12, fill="#10303bec", outline=MINT, width=2)
            text(draw, (430,530), "FOUR LINES!", 44, fill=MINT, bold=True)
        # A small progress track also communicates the clip's four chapters.
        for i, (begin,end,*_) in enumerate(CHAPTERS):
            x0 = 48+1822*begin/SECONDS
            x1 = 48+1822*end/SECONDS-7
            draw.rounded_rectangle((x0,1048,x1,1053), radius=2, fill="#253e4d")
            filled = x0+(x1-x0)*max(0,min(1,(now-begin)/(end-begin)))
            if filled>x0:
                draw.rounded_rectangle((x0,1048,filled,1053), radius=2, fill=MINT)
        return result


def main():
    OUT.mkdir(exist_ok=True); WORK.mkdir(exist_ok=True)
    composer = Composer()

    game = Game(seed=7)
    scene = None
    encoder = None
    evidence = []
    raw_markers = {0,90,134,140,146,180,230,300,375,419}
    try:
        for y in range(16,20):
            for x in range(10):
                if x!=4:
                    game.board[x,y] = (game.next_id,"IOTJLSZ"[(x+y)%7])
                    game.next_id += 1
        game.spatial.publish(game.board)
        game.active = Piece("I",x=2,y=3,rotation=0)
        game.command("start",0.)
        scene = RtxScene()
        scene.warm_up(game.snapshot(),threading.Event())
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        video = OUT / "Spatial-Blocks-RTX-Demo.mp4"
        command = [ffmpeg,"-hide_banner","-loglevel","error","-y","-f","rawvideo","-pixel_format","rgb24",
                   "-video_size",f"{WIDTH}x{HEIGHT}","-framerate",str(FPS),"-i","pipe:0","-an",
                   "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart",
                   "-metadata","title=Spatial Blocks — RTX Edition","-metadata","comment=Scripted native-library gameplay with explanatory captions; not a performance benchmark.",str(video)]
        with (WORK / "encoder.log").open("w") as log:
            encoder = subprocess.Popen(command,stdin=subprocess.PIPE,stderr=log,stdout=subprocess.DEVNULL)
            last_action = ("",-10.)
            for frame in range(FPS*SECONDS):
                now = frame/FPS
                for action in EVENTS.get(frame,[]):
                    before = game.snapshot()
                    game.command(action,now)
                    after = game.snapshot()
                    scene.effect(before,after,now,action=="drop")
                    last_action = (action,now)
                    evidence.append(dict(frame=frame,time=now,action=action,score=after["score"],lines=after["lines"],
                                         pieces=after["pieces"],queries=after["engine"]["queries"],scene_ordinal=after["engine"]["ordinal"]))
                before = game.snapshot()
                game.advance(now)
                state = game.snapshot()
                scene.effect(before,state,now)
                orbit = smooth((now-7.1)/3.8)
                scene.yaw = .178+.28*orbit-.07*smooth((now-12)/2)
                scene.pitch = .125+.075*orbit
                scene.update(state,now)
                pixels = scene.render()
                canvas = composer.compose(pixels,state,scene,now,last_action)
                encoder.stdin.write(canvas.tobytes())
                if frame in raw_markers:
                    canvas.save(WORK / f"frame-{frame:03}.jpg",quality=94)
                if frame%90==0:
                    print(f"Rendered {frame}/{FPS*SECONDS} frames; queries={state['engine']['queries']}; lines={state['lines']}",flush=True)
            encoder.stdin.close()
            if encoder.wait(timeout=90)!=0:
                raise RuntimeError((WORK / "encoder.log").read_text())
        assert game.lines==4 and game.pieces>=5, "The scripted clearance did not execute"
        assert game.phase=="playing", "Demo unexpectedly ended"
        summary = dict(video=str(video),duration=SECONDS,fps=FPS,frames=FPS*SECONDS,resolution=[WIDTH,HEIGHT],
                       input_mode="scripted through Game.command",scene="prepared four-line clearance",
                       render_engine="ovrtx",collision_engine="ovspatialquery",scene_engine="ovstage",
                       game=game.snapshot(),events=evidence,bytes=video.stat().st_size)
        (WORK / "capture-evidence.json").write_text(json.dumps(summary,indent=2))
        print(json.dumps({k:summary[k] for k in ("video","duration","fps","frames","resolution","bytes")}),flush=True)
    finally:
        if encoder is not None and encoder.poll() is None:
            encoder.kill(); encoder.wait()
        if scene is not None:
            scene.close()
        game.close()


if __name__=="__main__":
    main()
