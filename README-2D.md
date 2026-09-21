# Spatial Blocks - 2D Edition

See [README.md](README.md) for initial setup and the required access to the private ovspatialquery dependency.

**3D RTX edition:** launch **Play Spatial Blocks 3D.cmd**. See [README-3D.md](README-3D.md) for its visual features, camera controls, and renderer setup.

A small playable falling-block game using the real **ovspatialquery CPU library** for overlap tests. The display runs in your browser; Python owns the rules and calls the installed native DLL. No external web service is used. There is no substitute collision backend.

## Play

Double-click **Play Spatial Blocks.cmd**. The launcher reopens a running game or starts the local server. Click **Let's play** or press Enter. Use **Close game** at the bottom to shut down the server cleanly.

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

Switching to another browser tab automatically pauses the game. Touch buttons are available on narrow screens. Seven-bag randomization, standard wall-kick tables, a half-second lock delay, next-three preview, ghost landing, line clears, scores and increasing speed are included. T-spin, combo and competitive guideline scoring are outside this small demo.

## How the spatial library is used

`spatial_backend.py` registers one box definition and reuses it for every settled block. An explicit population contains settled blocks only. Movement, rotation and the landing preview call `overlap_any` with `EXACT` oriented-box queries. Board boundaries are checked arithmetically; the Python grid stores colors, identities and line membership, but is never the collision oracle.

Stored boxes are one unit wide. Query boxes are inset to 0.98 units so face-touching adjacent cells remain legal. Each lock/clear publishes an atomic changed/removed update with a new ordinal. Surviving blocks keep their identities when rows shift; removed identities are never reused. The sidebar displays real query counts, query duration and population version. Results are checked against the expected ordinal. Operations and resources are explicitly released.

`game.py` owns game rules; `app.py` exposes a loopback-only local server; `web/` contains the keyboard/touch UI and canvas renderer. No GPU, physics stepping or Ovstage scene is required by the game itself.

## Prerequisites and rebuild

This copy was built and tested against repository revision `3724a03cf5c5960b90fe7d4d9f1e27754c90fdfe` on Windows. The game uses the CPU explicit-population API; it is a small learning demo rather than a library performance benchmark.

The adjacent `ovspatialquery-prototype` checkout is the source used by the launcher. Its installed native package and Python environment are produced by:

```powershell
cd ..\ovspatialquery-prototype
.\dev.ps1 bootstrap -Scope Library
```

Follow that repository's prerequisites, including Visual Studio C++ Build Tools and access to its pinned dependency packages. The game uses NumPy from that environment and otherwise Python's standard library. It does not alter system Python. `OVSPATIALQUERY_REPO` and `OVSPATIALQUERY_LIBRARY` can explicitly override the repository and DLL locations.

For development, from this game's directory:

```powershell
& ..\ovspatialquery-prototype\_build\venv\ovspatialqueryapp\Scripts\python.exe app.py
& ..\ovspatialquery-prototype\_build\venv\ovspatialqueryapp\Scripts\python.exe -m unittest -v test_game
```

Tests exercise the real DLL, including adjacent cells, blocked moves, rotations, row compression, scoring, landing, pause, game over, and native resource cleanup. They do not load a mock spatial implementation. Runtime files (`runtime.json`, `game.log`) stay in this folder.

The 12 game integration tests passed. Browser checks also passed for movement, rotation, hard drop, pause/resume, restart, touch controls, and layouts down to 320 pixels wide, with no browser errors or external requests. `browser-check.cjs` can repeat those checks against a freshly started game when Playwright is available; set `PLAYWRIGHT_MODULE` and `CHROME_PATH` if those tools are installed outside the default paths. It writes screenshots to `qa-output/`.
