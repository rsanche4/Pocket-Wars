# Pocket Wars

A small turn-based war game: plastic army men, pixel dioramas, Game Boy Advance style. © 2026 RAFFY'S PLAYGROUND

Made with Python and **Pygame**.

## Setup and running

Python 3.12+ and pygame-ce:

    py -m pip install pygame-ce
    py main.py

Keys: ARROWS move, ENTER (or Z, SPACE) select, ESC (or X) back, F11 full screen.
Your settings are kept in `settings.json` (delete it to go back to the defaults).
What the Hard CPU has learned about you is kept in `learned.json` (Options → HARD'S MEMORY erases it, or delete the file).

## Folders

| Folder | What's in it | Change it? |
|---|---|---|
| `assets/` | every picture and sound the game uses | yes: replace any file with your own (same name) |
| `data/` | unit stats (`units.json`), CPU settings (`ai.json`), colours and battle-scene timing (`style.json`), font layout (`font.json`), the Manual and editor guide text (`howto.json`, `editor_help.json`), the tutorial's dialogue (`tutorial.json`) | yes |
| `maps/` | every map, one `.json` each: the built-in ones and the ones you save from the map editor (which can open and edit any of them). Share a map by sending its file; drop a friend's file in here to play it | yes: add or edit maps |
| `data/default-maps/` | untouched copies of the built-in maps, used by RESET TO DEFAULT (and to bring back deleted ones) | only if you want to change what "default" means |
| `pw/` | the Python code | |
| `tools/` | helper scripts: CPU simulations, the sound and music generators | |

## The code (`pw/`)

| File | Job |
|---|---|
| `data.py` | loads unit stats, CPU settings and maps (and saves your maps) |
| `rules.py` | the rules: one battle's state and every move a player can make. No drawing. |
| `ai.py` | the Normal and Hard CPU players (Hard thinks ahead on copies of the board and has several styles) |
| `learn.py` | Hard's memory of you: which styles beat you and which vehicles you build (`learned.json`) |
| `gfx.py` | the 320x240 screen, loading images, the pixel font, simple shapes |
| `world.py` | builds a map's ground from the terrain tiles |
| `field.py` | draws a battle: outposts, buildings, units, fog, cursor, marching groups |
| `cutin.py` | the battle scene when one unit attacks another |
| `menu.py` | the pop-up menu box |
| `play.py` | the battle screen: keys, menus, CPU turns, animations |
| `tutorial.py` | the TUTORIAL: its fixed path of lessons (only the move being taught is allowed), when each talk plays (words in `data/tutorial.json`), the talk box, and Tan's scripted turns until the hand-off |
| `stats.py` | BATTLE STATS after a battle: a report card and turn-by-turn charts (numbers kept by `rules.py`) |
| `title.py` | the title screen, its intro, the live battle behind it and the commanders |
| `menus.py` | choose a battlefield, battle setup, options |
| `howto.py` | the MANUAL (How to Play) and the editor's guide, with their pictures |
| `editor.py` | the map editor, the list of maps, and the GENERATE MAP screen |
| `mapgen.py` | the map generator: builds a fair, mirrored map from a few settings |
| `demo.py` | make-believe battles for the title and How to Play |
| `settings.py` | loads and saves `settings.json` |
| `sound.py` | plays sound effects and music from files (missing files are just silent) |

## Pictures you can swap without touching code

Every image is a file in `assets/`, including the font (`assets/ui/font.png`, letter order in `data/font.json`).
Pictures are drawn exactly as they are (never mirrored), so Tan's art should already face left.

Each unit has three pictures, one per size, named `<unit>_<side>.png` (e.g. `tank_tan.png`):
`assets/units/battle/` (battle scenes, shown at double size), `assets/units/map/` (the battlefield)
and `assets/units/icons/` (menus and the How to Play tables). The icons folder also has `hq_green.png` and
`hq_tan.png`, the little castle in the How to Play tables (the map and battle HQs are in `assets/buildings/`).

A few extras are optional:
- `assets/ui/title_backdrop.png` (320x240): a fixed picture behind the title instead of the live battle.
- `assets/howto/<picture>.png` (292x100): your own picture for a How to Play page (names are in `data/howto.json`).
- `assets/ui/keys/<key>.png` and `<key>_pressed.png`: the keyboard keys on the How to Play controls page.
- `assets/commanders/<folder>/title.png`: a strip of square frames that animates a commander on the title
  (speed: `title_anim_fps` in `data/style.json`); `blink.png` is their closed-eye face.

The battle screen's turn feedback is in `assets/ui/` too (`py tools/make_ui.py` made the originals; running it
again overwrites them, so pass names to remake only some, e.g. `py tools/make_ui.py arrow_head`):
- `cursor.png`: the white corners around the outpost you're on, centred on it like the target below. A strip of
  square frames it flips through to pulse (the original has 2: tight, then 1 pixel wider).
- `target.png`: the red target cursor while you choose what to attack, centred on the enemy outpost. A strip of
  square frames it flips through to pulse (the original has 2). `target_off.png`: the same over something you
  can't attack.
- `parachute_green.png`, `parachute_tan.png`: the canopy and cords above a soldier dropping in (also the
  see-through one showing where the next will land). The bottom middle is where the cords meet the soldier's head.
- `dust.png`: the puff when a soldier lands, a strip of square frames played left to right (bottom row = ground).
- `arrow_body.png`: the march arrow's body as a slice across it. Only its left column counts: top to bottom it's
  outline, fill, outline (any stripes you like); the game sweeps it along the road and rounds it at the bends.
  Its height is the arrow's thickness.
- `arrow_head.png`: the arrowhead on straight roads, pointing right with the tip on its right edge; the game
  turns it a quarter at a time to face up, down or left.
- `arrow_head_diagonal.png`: the arrowhead on diagonal roads, pointing down-right along the road with the tip in
  its bottom-right corner; the game flips it for the other three diagonal directions.
- `arrow_start.png`: the dot where the arrow starts.

The battle scenes happen outdoors:
- `assets/ui/sky.png` (320x186): the sky above the ground. Any size works (it's stretched to fit). For a sky that only
  one map theme uses, put a `sky.png` in that theme's folder, e.g. `assets/terrain/snow/sky.png`.
- `assets/ui/cloud1.png`, `cloud2.png`, `cloud3.png`: clouds that drift slowly across the sky, one picture each.
  Every `cloud*.png` in `assets/ui/` is used, so add `cloud4.png` for another, or delete them all for a clear sky.
- The ground is the map theme's own `ground.png`, with its `road.png` under the units when a road joins the two
  outposts, or its `water.png` (and `bridge.png`) between them when they fight across a river. Nothing extra to draw.

Between two neighbouring outposts with no road or river at all, the battlefield shows the theme's `blocked.png`
(`assets/terrain/<theme>/blocked.png`, about 34x30): a forest on grass, mountains on desert and snow, boulders on the
beach, so it's clear nobody can get through, not even a helicopter. Its bottom middle sits just below the middle of
the gap, and it's drawn over the outposts' pads but under their buildings and units, so treetops can overlap the
outpost above. `py tools/make_ui.py blocked_grass` (or `_desert`, `_beach`, `_snow`) remakes one.

Diagonal roads use the theme's `road_diagonal.png` (`assets/terrain/<theme>/road_diagonal.png`, 88x80): one diagonal
road going down-right from one outpost to the next, starting 10 pixels in from the top-left corner and ending 10 pixels
in from the bottom-right corner (its ends hide under the outposts). The game mirrors it for roads going down-left and
pastes it pixel for pixel, never stretched: on maps drawn a little bigger or smaller its ends reach a few pixels less or
further, so paint the road on out into the 10-pixel margin. The originals are just `road.png` turned at the angle; paint over
them for a cleaner diagonal (`py tools/make_ui.py road_diagonal_grass` remakes one from the current `road.png`).

The phase colours (rings, the top-bar tag and the big splash) are in `data/style.json`: `phase_gather` gold,
`phase_march` blue, `phase_attack` orange (choosing where to attack from), `phase_target` red (choosing a target).

## Sound effects

Every sound is a file in `assets/sfx/` (34 of them, e.g. `cursor.wav`, `shot_tank.wav`, `turn_green.wav`).
Replace any with your own: same name, WAV, OGG or MP3. A missing file is simply silent.
`tools/make_sfx.py` made the originals in a Game Boy Advance style; running it again overwrites them,
so only run it for names you haven't replaced (e.g. `py tools/make_sfx.py cursor select`).
Music is in `assets/music/` (`title`, `battle`, `victory`).

## Map files

    {"name": "Boot Camp", "theme": "grass", "blurb": "...", "art": ["o-G~G-o", "| | | |", "H-o=o-h", ...]}

`theme` is grass, desert, beach or snow. In `art`, outposts sit on even rows and columns:
`o` outpost, `G` barracks, `H` Green HQ, `h` Tan HQ. Between them: `-` `|` road, `~` river, `=` bridge,
and on odd rows and columns `/` `\` `X` diagonal roads.

## Tools

    py tools/sim.py --games 200 --level hard      # CPU vs CPU on every map, to check fairness
    py tools/make_sfx.py                          # remake the built-in sound effects
    py tools/make_ui.py                           # remake the target, parachute, dust, march arrow, sky and cloud pictures
    py tools/make_music.py                        # remake the placeholder music (needs numpy and ffmpeg)
