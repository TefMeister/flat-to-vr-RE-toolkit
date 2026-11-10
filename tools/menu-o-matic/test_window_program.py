"""Live test for the program check (2026-11-10): two windows with the same word in their titles, the wrong one in front.
Windows only; opens two small windows of its own for a few seconds, no game. Run: python test_window_program.py

What it stands in for: on the home PC `look "Fallout"` took a picture of the chat program, open on a thread called
"Fallout 3/NV VR | ...", and sent the quit keys at it, because the game's own window had another title at that moment.
Here the "chat" window is python.exe and the "game" is pythonw.exe; both titles contain "Fallout", the chat window is
the bigger one (the old rule took the largest match) and it is in front.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mom_window as W  # noqa: E402

FAILS = []
CHAT_TITLE, GAME_TITLE = "Fallout 3/NV VR | chat thread (test)", "Fallout test game (test)"
START_WAIT_S = 15

WINDOW = r'''
import sys, tkinter as tk
title, log, geo = sys.argv[1], sys.argv[2], sys.argv[3]
r = tk.Tk(); r.title(title); r.geometry(geo)
def key(e):
    with open(log, "a") as f: f.write(e.keysym + "\n")
r.bind("<Key>", key)
r.after(60000, r.destroy)
r.after(300, lambda: (r.lift(), r.focus_force()) if "chat" in title else None)
r.mainloop()
'''


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({extra})" if extra and not cond else ""))
    if not cond:
        FAILS.append(name)


def mom(*args):
    r = subprocess.run([sys.executable, os.path.join(HERE, "menu_o_matic.py"), *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def keys(log):
    return open(log).read().split() if os.path.isfile(log) else []


def main():
    tmp = tempfile.mkdtemp(prefix="mom-exe-")
    script = os.path.join(tmp, "window.py")
    open(script, "w").write(WINDOW)
    chat_log, game_log = os.path.join(tmp, "chat.txt"), os.path.join(tmp, "game.txt")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    game = subprocess.Popen([pythonw, script, GAME_TITLE, game_log, "360x240+900+120"])
    time.sleep(1.5)
    chat = subprocess.Popen([sys.executable, script, CHAT_TITLE, chat_log, "820x520+60+60"])
    try:
        end = time.time() + START_WAIT_S
        while time.time() < end and not (W.find_window(CHAT_TITLE, exe="") and W.find_window(GAME_TITLE, exe="")):
            time.sleep(0.3)
        chat_h, game_h = W.find_window(CHAT_TITLE, exe=""), W.find_window(GAME_TITLE, exe="")
        check("both test windows opened", bool(chat_h and game_h))
        if not (chat_h and game_h):
            return
        time.sleep(0.8)
        check("the chat window is in front", W.in_front(chat_h))
        check("program_of names each program",
              W.program_of(chat_h) == os.path.basename(sys.executable).lower() and W.program_of(game_h) == "pythonw.exe",
              f"{W.program_of(chat_h)}, {W.program_of(game_h)}")

        # the old way: the title alone takes the wrong window (the bigger one)
        check("control: by title alone 'Fallout' finds the chat window", W.find_window("Fallout", exe="") == chat_h)
        # the program check
        check("with exe pythonw.exe 'Fallout' finds the game window", W.find_window("Fallout", exe="pythonw.exe") == game_h)
        check("a program name alone finds the game window", W.find_window("pythonw.exe") == game_h)
        check("with exe FalloutNV.exe nothing is found", W.find_window("Fallout", exe="FalloutNV.exe") is None)
        line = W.missing("Fallout", exe="FalloutNV.exe")
        check("the refusal names the chat window and its program", "chat thread" in line and "belongs to" in line, line)

        # the commands, as the home PC would type them: each refused, nothing reaches the chat window
        for cmd in (["press", "Fallout", "q"], ["look", "Fallout", os.path.join(tmp, "x.png")],
                    ["click", "Fallout", "0.5,0.5"]):
            code, out = mom(*cmd, "--exe", "FalloutNV.exe")
            check(f"{cmd[0]} --exe FalloutNV.exe is refused", code == 1 and "belongs to" in out, out.strip()[-160:])
        check("no picture was taken", not os.path.isfile(os.path.join(tmp, "x.png")))
        time.sleep(0.5)
        check("no key reached the chat window", keys(chat_log) == [], keys(chat_log))

        # a route file that names the program: the key goes to the game, not to the chat window in front
        route = os.path.join(tmp, "route.json")
        code, out = mom("new", route, "--game", "test", "--window", "Fallout", "--route", "t", "--exe", "pythonw.exe")
        check("new --exe stores the program in the route", code == 0 and json.load(open(route)).get("exe") == "pythonw.exe",
              out.strip()[-160:])
        code, out = mom("press", "Fallout", "q", "--route", route)
        time.sleep(0.8)
        check("press with that route sends the key to the game window", code == 0 and keys(game_log) == ["q"],
              f"exit {code}, game keys {keys(game_log)}, {out.strip()[-160:]}")
        check("and still nothing to the chat window", keys(chat_log) == [], keys(chat_log))
    finally:
        for p in (chat, game):
            p.kill()
    print("\nall passed" if not FAILS else f"\n{len(FAILS)} FAILED: {', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
