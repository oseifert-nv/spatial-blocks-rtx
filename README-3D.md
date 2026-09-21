# Spatial Blocks — RTX Edition

Double-click **Play Spatial Blocks 3D.cmd**. The launcher starts the local renderer and opens the game in your browser. Press Enter or click **Let's play**. The original 2D launcher remains available.

This edition keeps the classic 10 × 20 game rules and presents the board as actual 3D geometry. **ovrtx renders the scene on the NVIDIA GPU**, **ovstage owns and updates that scene**, and **ovspatialquery checks block placement on the CPU**. The browser displays the rendered frames and the interface.

## Controls

| Control | Action |
|---|---|
| Left / right, A / D | Move |
| Up, W, X | Rotate clockwise |
| Z, Q | Rotate counterclockwise |
| Down, S | Soft drop |
| Space | Hard drop |
| P, Escape | Pause / resume |
| Enter | Start / resume / play again |
| R | New game |
| Drag the scene | Orbit the camera |
| Scroll over the scene | Zoom |
| 1 / 2 | Front / perspective view |

Switching tabs pauses play. The **Close game** button stops the renderer and releases native resources. The frame rate is capped at 30 during play and reduced to 12 while ready or paused; actual performance depends on the GPU, rendering, readback, and display overhead.

## Visuals

- Beveled cube meshes with seven colored alloy textures and fine roughness variation.
- A machined frame, reflective floor, recessed board grid, and three area lights.
- Real-time path-traced shading, reflections and shadows, plus subtle ovrtx bloom.
- A 3D wireframe landing guide and floating previews of the next three pieces.
- Light trails on hard drops, expanding beams on line clears, and animated sparks.
- Front and orbitable perspective views, with the board's logical coordinates independent of the camera.

All game textures are generated locally. The game scene needs no remote assets. The GPU frame is copied through DLPack, encoded as JPEG, and displayed over a loopback HTTP connection. This is a local desktop application; the server binds only to `127.0.0.1`.

## Source map

| File | Responsibility |
|---|---|
| `game.py`, `spatial_backend.py` | Shared game rules and real native overlap queries |
| `scene3d.py` | Builds `assets3d/board.usda`, beveled meshes, lights and texture maps |
| `renderer3d.py` | ovstage transform/material updates, ovrtx rendering and 3D effects |
| `app3d.py` | One owner thread for gameplay and native rendering; queued browser input |
| `web3d/` | Interface, controls, camera input, and display of rendered images |

Settled pieces, active pieces, preview pieces, ghosts, sparks and beams use preallocated scene objects. Persistent ovstage queries update their transforms. Material bindings choose among the seven preloaded material graphs. Each scene update receives a new ordinal, is sealed with `advance_write_floor`, and is rendered at that ordinal. Mapped frame memory is copied and unmapped before advancing; shutdown releases queries, detaches ovstage, and destroys the stage and renderer.

## Environment

Tested on Windows with an NVIDIA RTX A6000 and driver 597.06. This edition requires an RTX-capable GPU and a supported NVIDIA driver; see the [ovrtx driver requirements](https://nvidia-omniverse.github.io/ovrtx/driver_requirements.html). Its separate `.venv3d` environment uses Python 3.12 and the matching release train:

- ovrtx `0.5.0.377615`
- ovstage `0.2.0.377349`
- NumPy `2.2.6`, Pillow `12.1.1`, usd-core `26.8`

The installed ovspatialquery DLL is shared with the original game. See [README.md](README.md) for access requirements and setup, and [README-2D.md](README-2D.md) for details of its spatial backend. The 3D environment does not modify the original game's environment.

To recreate the Windows renderer environment with a Python 3.12 interpreter:

```powershell
python -m venv .venv3d
& .\.venv3d\Scripts\python.exe -m pip install -r requirements3d.txt
& .\.venv3d\Scripts\python.exe scene3d.py
```

The renderer download is about 1.2 GB. The first GPU initialization compiles shaders and can take several minutes; subsequent starts use the cache. The game page displays a startup state until the renderer is ready. Rendering must run with access to the GPU and driver. Runtime diagnostics are written to `game3d.log`; `runtime3d.json` records the current local address.

## Verification

The official ovrtx Python minimal example rendered successfully and was visually compared with its reference. The twelve shared game integration tests passed in the 3D environment. Browser integration verifies real JPEG frames, native collision checks, a four-row clear, active particles, changing rendered output, movement, rotation, pause, camera views, orbit, restart, touch controls and request-origin restrictions.

```powershell
& .\.venv3d\Scripts\python.exe -m unittest -v test_game
& .\.venv3d\Scripts\python.exe renderer3d.py
```

For the browser check, start `app3d.py --seed 7 --test-scenario`, then run `browser-check3d.cjs` with Playwright and Chrome available. `PLAYWRIGHT_MODULE` and `CHROME_PATH` can specify their installed paths. The test scenario starts with a prepared four-row clearance and is never enabled by the normal launcher. Verification screenshots are saved in `qa-output/`.
