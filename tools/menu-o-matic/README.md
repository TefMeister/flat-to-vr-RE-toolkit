# Menu-o-matiC

**Gets a game from launch to gameplay by itself (and back out), by replaying recorded menu routes.**
Built for flat-to-VR modding sessions, where the same menus get walked dozens of times a day. Works for any
person or AI that can run a command; a model is only needed when something unexpected is on screen.
Windows only. Needs Python 3 and Pillow (`pip install pillow`).

## How it works

A **route** is a recorded way through a game's menus: press Enter, wait for the main menu, press Down, wait for
"Options" to be highlighted, and so on. Each "wait for" is a **checkpoint**: a small rectangle of the window plus a
fingerprint of what it looked like (the patch shrunk to 32×32 grey levels, 1,024 numbers). While replaying, the
tool compares the live patch with the fingerprint about twice a second. That comparison is plain arithmetic, so a
replay costs **no model tokens at all**. The tool stops and saves two small pictures only when a checkpoint does not
match in time, and that is the moment a person or an AI needs to look.

No picture of the game is ever stored in a route, only the fingerprints, so routes can be shared publicly.

## Recording a route cheaply

The expensive part of automating a game is looking at it. Menu-o-matiC keeps the looking small:

1. **Look once, small:** `look <window> full.png --scale 0.5` (a half-size picture costs a quarter of a full one).
2. **Let the tool find the choices:** `press <window> down --changed crop.png`. It takes two pictures before the key
   (anything that differs between those two is moving by itself, such as an animated background or a blinking cursor,
   and is ignored), presses the key, takes one after, and saves **only the patch that changed**. That patch is
   normally the menu lines themselves. Read the crop, not the screen.
3. **Keep reading crops.** `look <window> crop.png --region x,y,w,h` shows the same patch again after each key. Take a
   bigger picture only when a crop stops making sense (a new screen, a pop-up).
4. **Mark each screen as you reach it:** `mark <window> route.json main_menu --region x,y,w,h --note "Main menu,
   Continue highlighted"`. Choose a patch of text or icons that does not animate.
5. **Next time, `run route.json`** replays it with no pictures at all.

Regions are fractions of the window (`x,y,width,height`, each 0 to 1), so a route recorded in one window size
replays in another.

## Two settings that real games needed

- **Keys are held for 0.15 s.** A game that reads the keyboard once per frame can miss a shorter press when it runs
  slowly; Burnout Paradise did at 0.07 s.
- **`"repress": N` on a wait step** presses the previous key again if the screen has not arrived after N seconds.
  Some screens ignore a key while they are still fading in (Burnout's title screen does). Add it by editing the route
  file: `{"wait": "save_notice", "repress": 4}`.

## Commands

```
python menu_o_matic.py new   route.json --game "Burnout Paradise" --window "Burnout(TM)" --route launch_to_city
python menu_o_matic.py add   route.json --launch steam://rungameid/1238080
python menu_o_matic.py add   route.json --sleep 5
python menu_o_matic.py look  "Burnout(TM)" full.png --scale 0.5
python menu_o_matic.py look  "Burnout(TM)" crop.png --region 0.25,0.4,0.5,0.35
python menu_o_matic.py press "Burnout(TM)" enter --route route.json --changed crop.png
python menu_o_matic.py mark  "Burnout(TM)" route.json main_menu --region 0.25,0.4,0.5,0.35 --note "..."
python menu_o_matic.py check "Burnout(TM)" route.json main_menu
python menu_o_matic.py run   route.json [--from N] [--timeout 90] [--lost-dir DIR]
```

Every command prints one JSON line per event, so another program or an AI can read the result. `run` exits with
**0** when the route is done, **2** when it got lost (the JSON names the checkpoint, the difference, and the two
pictures it saved), and **1** for anything else.

## Safety

- **Keys only ever go to the named window.** Before every key and every picture the tool brings the window to the
  front, and if Windows refuses, it sends nothing and stops with an error. (On the day it was built, a plain "bring to
  front" failed once and a key landed in a web browser instead; that is why.)
- **Nothing is deleted or changed in the game.** The tool only presses keys and reads the screen.
- A checkpoint matches only when the patch is close on average **and** no single spot differs a lot, so one changed
  digit ("Col 2" against "Col 3") is enough to tell two screens apart.

## Where routes live

Recorded routes belong with each game's control profile in `ai-game-control-profiles`
(`routes/<game>/<route>.json`), next to the prose routes and hazards already written there.

## Tests

`python test_menu_o_matic.py` checks the route logic with drawn test pictures, no window or game needed (23 checks,
and a deliberately broken comparison makes it fail). Tried live on 2026-09-28 against Notepad: a recorded route
replayed correctly, and a route that typed one letter too many stopped with "lost" at the right checkpoint.
**First game, the same day: Burnout Paradise Remastered**, from a closed game to driving in the city in 150 seconds,
seven checkpoints, no pictures looked at (`ai-game-control-profiles/routes/burnout-paradise-remastered/launch_to_city.json`).

## Credits

The window capture and scancode key presses come from this toolkit's `game-harness.py`. Part of the Lanes plugin as
the `/lanes:menu` command. The idea, the name and the "look big once, then only small patches" approach came from
the person this toolkit is built with.
