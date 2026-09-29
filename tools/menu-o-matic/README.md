# Menu-o-matiC, Move-o-matiC and State-o-matiC

**Get a game from launch to gameplay by itself, and move the character or car along a recorded route, by
replaying what a person did once.** `menu_o_matic.py` is the menus; `move_o_matic.py` adds held keys and camera
turns. Both use the same route files and replay engine.
Built for flat-to-VR modding sessions, where the same menus get walked dozens of times a day. Works for any
person or AI that can run a command; a model is only needed when something unexpected is on screen.
Windows only. Needs Python 3 and Pillow (`pip install pillow`).

## Setting a game up (once, with the person who plays it)

**First, the game runs in a window, and the person confirms it.** `windowcheck <window>` measures the window and the screen (a game told only a size may switch the whole display and run fullscreen; the window then measures right and is still fullscreen). Then ask the person whether it is in a window of the right size and whether they can still see the session beside it. Their answer settles it. A fullscreen game hides the session from them. **Once per game:** `windowcheck <window> --route route.json --confirmed` stores their yes, and after that the check only measures and asks again only if the window changes size.

Automation only works when the basics come from someone who knows the game. Guessing costs whole sessions: on
the day this was written, a car was tapped forward for half an hour when it needed the throttle HELD, and a
tool waited for an intro video while "Press Any Button" was already on screen. So each game starts with a short
setup, done together:

1. **A save past the tutorials** that always loads in the same spot. Check it does: some games put you back
   wherever you last stopped, and then a recorded drive starts somewhere else. The person plays to it and says which
   slot it is (`note route.json "..."` keeps it in the route).
2. **The menus: three goals per game** (the player's scheme, 2026-09-29): **launch → gameplay**, **launch → key
   bindings** (pictured, read once, stored as `controls`), and **gameplay → desktop**. Each is recorded on its own,
   the quickest way through, with the three recorder keys below.
3. **The controls.** The person names the minimum buttons to move and look, and how they behave ("hold W about a
   second before the car moves"). Keep it with `note`.
4. **The input check.** Before recording anything, `probe <window> w --seconds 1.5 --region x,y,w,h` holds each
   control and says whether the pointed-at spot changed (brake lights, a speedometer, the character) and, with
   `--watch-file`, whether a mod's log wrote anything. If a key reaches the game but the screen looks the same,
   that is known at once instead of being mistaken for a slow load.
5. **The test brief, before any movement is recorded.** The person asked for this on the first Burnout drive
   (2026-09-29): *what is the test for, how far does it move, does it turn?* `brief route.json --why ..
   --start .. --move .. --move .. --screen .. --avoid .. --end ..` writes down exactly what has to happen on
   screen for the test to gather its data, and `brief route.json` prints it as a short numbered sheet. `record`
   prints it first, so the person plays what the test needs instead of a drive that happens to be recorded.
   Also note anything about the game world that changes between runs (Burnout's clock runs on, so a night
   recording replays in daylight): checkpoints should then sit on something that does not change with it,
   such as an on-screen map.
6. **A rehearsal first, on a game's first recording** (the player's rule, 2026-09-29). The person launches the
   game once themselves, when they are ready, and plays the route with nothing recording, paying attention to
   (or writing down) every button each screen needs. Only then is it recorded, so the recording holds no
   mistaken presses and no guessing. `record` says so when a route has no key steps yet.
7. **The person plays the route once while it is recorded, with three keys** (the player's scheme, 2026-09-29):
   **Home** starts recording (it may be pressed BEFORE the game starts, so skippable logos are caught);
   **Page Down** means "the next key I press is a step": a picture of the game window is taken at that moment and
   the very next key is recorded as the one that gets past the screen; **End** stops (a last picture shows where the
   route ended). Every other key is ignored, so stray presses never reach a route; if something goes wrong, the
   whole goal is simply recorded again. The three keys never reach the game (grey keys only). Then
   `mark-image route.json N name --region x,y,w,h` turns each step's picture into a checkpoint, so a replay waits
   for that screen and then presses its key. (Until 2026-09-29 the recorder kept every key with its timing and
   used Page Up/Page Down to mark screens; a replay of that shape got stuck on a load screen, and the player asked
   for this simpler one.) Old games that look up and down with Page Up/Down or Home/End cannot record those keys.

After that, `run` repeats it as often as needed with no pictures, waiting at each checkpoint so a slow load never
throws the timing off. If a replay drifts, it stops with "lost"; load the save again (its own short route) rather
than restarting the game. The recorder ignores keys that programs send, so a replay is never recorded by mistake.
Keyboard only for now: mouse movement is not recorded yet.

## A map of routes, not one route (2026-09-29)

The player's idea: Menu-o-matiC is not only "launch to gameplay". Each game gets **a set of named routes, each with a start and an end** (`new ... --from closed --to keybindings`), and `routes <folder>` lists them as a map, so they can be chained (`run launch_to_gameplay.json gameplay_to_x.json`). Typical first routes:

1. `closed -> gameplay`: the everyday one.
2. `closed -> keybindings`: the controls page. It ends with `picture` steps (`add FILE --picture NAME`), which save what the screen shows; they are read ONCE and the keys are stored in the route (`controls`), so a movement recording knows the controls without asking. (A game that keeps its keys in a settings file: read the file instead.)
3. Any other setting that has to be reached quickly (graphics, subtitles, a debug page).
4. `gameplay -> closed`: quitting through the game's own menu.

Move-o-matiC uses the same idea: short named movement routes, each from a known spot (a checkpoint the game can restore) to another, recorded at different times and in different conditions.

First game with a map: Prototype, 2026-09-29 (closed → gameplay 62 s, closed → key bindings 65 s with two pictures, gameplay → closed).

## Games that are awkward to drive (2026-09-29, Manhunt)

- **Keys that SendInput never reaches.** Some games only read keyboard *window messages*. A route's `"key_input"` picks the delivery: `"sendinput"` (default), `"post"` (PostMessage WM_KEYDOWN/WM_KEYUP to the game window) or `"both"`. The recorder is unaffected: the person's real keyboard reaches every game.
- **A launcher dialog before the game.** `add FILE --button Play --dialog "Manhunt launcher"` presses the button with BM_CLICK (no mouse, no focus; ANSI dialogs are read correctly). Give the launch step `"wait_for": "<launcher title>"` so it waits for the dialog rather than the game window.
- **Two windows with the same name.** A window title starting with `=` must match exactly: `=MANHUNT` is the game, not "Manhunt launcher".
- **A game whose own exit is closing its window.** `{"close": true}` sends WM_CLOSE and waits for it to go; never a kill.

Manhunt, recorded with the player on the keyboard: closed game → playing in 22-25 s, twice, every checkpoint matched.

## State-o-matiC: what is the game doing right now?

`state_o_matic.py watch <window> [--poke KEY] [--states FILE]` looks for two seconds and says **menu or loading
screen, loading, cutscene, gameplay, moving,** or **still**, with the reason. No game announces its state, so it
combines signs that work from outside almost any game, judged on this PC with no model involved:

| Sign | Means |
| --- | --- |
| black bars at the top and bottom | a cutscene |
| most of the picture changing | gameplay or a cutscene |
| only one small patch changing | a loading icon or a menu highlight |
| the game reading its disk hard | loading |
| `--poke KEY`: the picture answers a key | gameplay (even when nothing else moves) |
| a screen taught during setup (`teach`) | that screen, for certain |

**Teach the screens that fool it.** Menus with a moving 3D scene behind them look like gameplay, and a parked car
looks like a menu. During setup, show it those screens: `teach <window> states.json main_menu --region x,y,w,h`.
Menu-o-matiC and Move-o-matiC add its verdict when a route gets lost, so the report says "loading" or "cutscene"
rather than only "wrong screen". First live run: Burnout Paradise, 2026-09-28 (loading screens and the idle
cinematic camera were read correctly; the car screens and the parked view needed teaching).

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

## When things go wrong

A wait keeps trying for its whole time limit (90 s by default; `--timeout` for the whole run, or `"timeout"` on one
step), so a loading screen that is slower than usual is fine. While it waits, it also checks on every look:

| What happened | What the tool says | Exit code |
| --- | --- | --- |
| The screen never came, but the picture was still moving | `lost`: "a different screen than expected", plus a small patch and a half-size picture | 2 |
| The whole picture did not change at all for 30 s or more | `lost`: "frozen: the whole picture has not changed for N s" | 2 |
| The game window closed in the middle (a crash, or it quit) | `gone`, straight away, without waiting out the time limit | 3 |
| The game never opened a window after launching (4 minutes by default) | `gone`: "it did not start, or it crashed while starting" | 3 |
| Windows marked the game "Not Responding" for a whole minute | `not_responding` | 4 |

A frozen picture never cuts a wait short, because some loading screens really are still pictures; it only explains
the timeout. Tested on Notepad for all rows except "Not Responding", which needs a hung program to test.

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
python menu_o_matic.py click "Burnout(TM)" 0.5,0.62 --route route.json
python menu_o_matic.py mark  "Burnout(TM)" route.json main_menu --region 0.25,0.4,0.5,0.35 --note "..."
python menu_o_matic.py check "Burnout(TM)" route.json main_menu
python menu_o_matic.py run   route.json [--from N] [--timeout 90] [--lost-dir DIR]
```

Every command prints one JSON line per event, so another program or an AI can read the result. `run` exits with
**0** when the route is done, **2** when it got lost, **3** when the game window closed or never opened, **4** when
the game stopped responding, and **1** for anything else (see "When things go wrong").

## Safety

- **Keys only ever go to the named window.** Before every key and every picture the tool brings the window to the
  front, and if Windows refuses, it sends nothing and stops with an error. (On the day it was built, a plain "bring to
  front" failed once and a key landed in a web browser instead; that is why.)
- **Nothing is deleted or changed in the game.** The tool only presses keys and reads the screen.
- A checkpoint matches only when the patch is close on average **and** no single spot differs a lot, so one changed
  digit ("Col 2" against "Col 3") is enough to tell two screens apart.

## Which inputs a route can hold

Each step saves exactly the input that was used, so every menu gets its own button:

- **Keys:** Enter, Space, Esc, Tab, Backspace, the arrows, Home/End/Page Up/Page Down, Shift/Ctrl/Alt, F1 to F12,
  the numpad, letters and digits (`{"key": "space"}`).
- **Mouse clicks** at a point given as fractions of the window, so they still land right in another window size
  (`{"click": [0.5, 0.62]}`).
- **Not yet:** holding a key, mouse movement without a click, and **game controllers**. A menu that only answers a
  pad would need the toolkit's virtual pad (`virtual-pad.py`) joined in.

## Where routes live

Recorded routes belong with each game's control profile in `ai-game-control-profiles`
(`routes/<game>/<route>.json`), next to the prose routes and hazards already written there.

## Tests

**First game set up together: Burnout Paradise, 2026-09-28.** The player played from launch to driving in the city
once while it recorded; the recording showed what guessing had missed ("Press Any Button" appears a moment after the
title, and Enter before it is ignored). The route then replayed from a closed game twice in a row, 118 s and 161 s,
every checkpoint matched, no key pressed twice.

The recorder was tried on Notepad the same day: recorded typing (a held key, a tap, a marker) replayed from a
closed Notepad with the same result, and its marker became a working checkpoint.

`python test_menu_o_matic.py` checks the route logic with drawn test pictures, no window or game needed (47 checks,
and a deliberately broken comparison makes it fail). Tried live on 2026-09-28 against Notepad: a recorded route
replayed correctly, and a route that typed one letter too many stopped with "lost" at the right checkpoint.
**Second game, 2026-09-29: Alice: Madness Returns**, recorded with the player in one go (11 marks, 5 kept as checkpoints; the moving logos are simply waited out), then replayed from a closed game twice: 50 s each, every checkpoint matched. It showed that a game can open its window empty for a moment; a wait now keeps waiting through that instead of stopping.
**First game, the same day: Burnout Paradise Remastered**, from a closed game to driving in the city in 150 seconds,
seven checkpoints, no pictures looked at (`ai-game-control-profiles/routes/burnout-paradise-remastered/launch_to_city.json`).

## Credits

The window capture and scancode key presses come from this toolkit's `game-harness.py`. Part of the Lanes plugin as
the `/lanes:menu` command. The idea, the name and the "look big once, then only small patches" approach came from
the person this toolkit is built with.
