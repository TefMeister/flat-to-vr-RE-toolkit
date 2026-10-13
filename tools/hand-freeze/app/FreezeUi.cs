// FreezeUi.cs -- the Hand Freeze window, drawn by hand onto a small canvas and scaled up with hard pixel edges, so the
// whole window is pixel art (Tefa 2026-10-13: "if you can, make it look pixelated").
//
// Top: the title and a ROUND switch, red when OFF, fading smoothly to green when ON. Behind everything a looping
// background: summer (summer.gif) while OFF, a frozen winter (winter.gif) while ON. Then the seconds picker, then three
// rows, LEFT HAND, RIGHT HAND and BOTH HANDS, each with a snowflake-shaped FREEZE button and a flame-shaped UN- / FREEZE
// button. During a countdown the snowflake shows the seconds left; a frozen row's label turns icy. The font is Silkscreen
// (a pixel font, SIL OFL), embedded in the exe with the two backgrounds. It is drawn only at its own pixel sizes, 8 and
// 16, so every letter stays sharp and apart (Marcellus ran letters together at small sizes: Tefa, 2026-10-13).
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

class FreezeUi : Form {
    // ---- canvas and layout (canvas pixels; the window shows each one as SCALE x SCALE screen pixels) --------------
    const int CANVAS_W = 210, CANVAS_H = 300;   // must match make_backgrounds.py W, H
    const int SWITCH_X = 178, SWITCH_Y = 26, SWITCH_R = 19;
    const int SECONDS_Y = 76;
    const int ROW_Y0 = 98, ROW_H = 62, LABEL_X = 10, FLAKE_X = 110, FLAME_X = 170, FLAKE_R = 29;
    const int STATUS_Y = 286;
    const int FRAME_MS = 140;               // background frame time (make_backgrounds.py FRAME_MS)
    const int FADE_MS = 500;                // red <-> green switch fade
    const int DEFAULT_SECONDS = 10, MAX_SECONDS = 60;
    const int TICK_HZ = 880, TICK_MS = 70, FROZEN_HZ = 1320, FROZEN_MS = 350;   // the countdown beeps, the final one

    static readonly Color Red = Color.FromArgb(205, 60, 55), Green = Color.FromArgb(60, 185, 85);
    static readonly Color Ink = Color.FromArgb(20, 22, 34), Paper = Color.FromArgb(250, 250, 245);
    static readonly Color Ice = Color.FromArgb(170, 225, 255), IceDeep = Color.FromArgb(40, 110, 190);
    static readonly Color FlameOut = Color.FromArgb(225, 75, 35), FlameIn = Color.FromArgb(255, 200, 60), FlameEdge = Color.FromArgb(110, 25, 15);

    readonly Shared shared = new Shared();
    readonly System.Windows.Forms.Timer tick = new System.Windows.Forms.Timer();
    readonly Bitmap canvas = new Bitmap(CANVAS_W, CANVAS_H, PixelFormat.Format32bppArgb);
    readonly List<Bitmap> summer, winter;
    readonly PrivateFontCollection fonts = new PrivateFontCollection();
    readonly FontFamily face;
    readonly int scale;
    readonly string settingsFile = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "settings.txt");
    readonly DateTime started = DateTime.Now;

    bool on;
    float fade;                 // 0 = red/summer, 1 = green/winter, eased towards `on`
    DateTime lastTick = DateTime.Now;
    int seconds = DEFAULT_SECONDS;
    bool pinned;
    int countdownHands;         // which hands the running countdown will freeze; 0 = none
    DateTime countdownEnd;
    int lastBeep = -1;
    string hover = "", pressed = "";

    struct Row { public string Label, Noun; public int Hands; public int Y; }
    static readonly Row[] Rows = {
        new Row { Label = "LEFT", Noun = "HAND", Hands = Hands.LEFT, Y = ROW_Y0 },
        new Row { Label = "RIGHT", Noun = "HAND", Hands = Hands.RIGHT, Y = ROW_Y0 + ROW_H },
        new Row { Label = "BOTH", Noun = "HANDS", Hands = Hands.BOTH, Y = ROW_Y0 + 2 * ROW_H },
    };

    public FreezeUi() {
        Text = "Hand Freeze";
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
        FormBorderStyle = FormBorderStyle.FixedSingle; MaximizeBox = false;
        DoubleBuffered = true;
        using (var g = CreateGraphics()) scale = Math.Max(2, (int)Math.Round(2 * g.DpiX / 96f));
        ClientSize = new Size(CANVAS_W * scale, CANVAS_H * scale);

        face = LoadFont("Silkscreen-Regular.ttf");
        summer = LoadFrames("summer.gif");
        winter = LoadFrames("winter.gif");
        on = Layer.IsOn();
        fade = on ? 1 : 0;
        LoadSettings();
        TopMost = pinned;

        tick.Interval = 40;
        tick.Tick += (s, e) => Step();
        tick.Start();
        MouseMove += (s, e) => { string h = HitTest(e.Location); if (h != hover) { hover = h; Cursor = h != "" ? Cursors.Hand : Cursors.Default; Invalidate(); } };
        MouseLeave += (s, e) => { hover = ""; Invalidate(); };
        MouseDown += (s, e) => { pressed = HitTest(e.Location); Invalidate(); };
        MouseUp += (s, e) => { string h = HitTest(e.Location); if (h != "" && h == pressed) Press(h); pressed = ""; Invalidate(); };
        MouseWheel += (s, e) => { if (on) SetSeconds(seconds + Math.Sign(e.Delta)); };
        FormClosing += (s, e) => { shared.Unfreeze(Hands.BOTH); shared.Dispose(); };
    }

    // ---- resources -------------------------------------------------------------------------------------------------
    static Stream Resource(string name) { return Assembly.GetExecutingAssembly().GetManifestResourceStream(name); }

    FontFamily LoadFont(string name) {
        try {
            using (var s = Resource(name)) {
                var bytes = new byte[s.Length];
                s.Read(bytes, 0, bytes.Length);
                IntPtr mem = Marshal.AllocCoTaskMem(bytes.Length);   // GDI+ keeps reading it: never freed, on purpose
                Marshal.Copy(bytes, 0, mem, bytes.Length);
                fonts.AddMemoryFont(mem, bytes.Length);
                return fonts.Families[0];
            }
        } catch { return new FontFamily("Candara"); }
    }

    static List<Bitmap> LoadFrames(string name) {
        var list = new List<Bitmap>();
        try {
            using (var s = Resource(name))
            using (var gif = Image.FromStream(s)) {
                var dim = new FrameDimension(gif.FrameDimensionsList[0]);
                int n = gif.GetFrameCount(dim);
                for (int i = 0; i < n; i++) { gif.SelectActiveFrame(dim, i); list.Add(new Bitmap(gif)); }
            }
        } catch { }
        if (list.Count == 0) list.Add(new Bitmap(CANVAS_W, CANVAS_H));
        return list;
    }

    void LoadSettings() {
        try {
            var lines = File.ReadAllLines(settingsFile);
            int v;
            if (lines.Length > 0 && int.TryParse(lines[0].Trim(), out v) && v >= 0 && v <= MAX_SECONDS) seconds = v;
            pinned = lines.Length > 1 && lines[1].Trim() == "pinned";
        } catch { }
    }
    void SaveSettings() { try { File.WriteAllLines(settingsFile, new[] { seconds.ToString(), pinned ? "pinned" : "free" }); } catch { } }

    // ---- behaviour -------------------------------------------------------------------------------------------------
    void Step() {
        var now = DateTime.Now;
        float dt = (float)(now - lastTick).TotalMilliseconds;
        lastTick = now;
        float target = on ? 1 : 0;
        fade += Math.Sign(target - fade) * Math.Min(Math.Abs(target - fade), dt / FADE_MS);
        if (countdownHands != 0) {
            double left = (countdownEnd - now).TotalSeconds;
            if (left <= 0) {
                shared.Freeze(countdownHands);
                countdownHands = 0;
                Beep(FROZEN_HZ, FROZEN_MS);
            } else {
                int whole = (int)Math.Ceiling(left);
                if (whole != lastBeep) { lastBeep = whole; Beep(TICK_HZ, TICK_MS); }
            }
        }
        Invalidate();
    }

    void Press(string what) {
        if (what == "switch") { Toggle(); return; }
        if (what == "pin") { pinned = !pinned; TopMost = pinned; SaveSettings(); return; }
        if (!on) return;
        if (what == "minus") { SetSeconds(seconds - 1); return; }
        if (what == "plus") { SetSeconds(seconds + 1); return; }
        foreach (var r in Rows) {
            if (what == "freeze" + r.Hands) {
                countdownHands = r.Hands;
                countdownEnd = DateTime.Now.AddSeconds(seconds);
                lastBeep = -1;
                if (seconds == 0) Step();
            } else if (what == "unfreeze" + r.Hands) {
                if ((countdownHands & r.Hands) != 0) countdownHands = 0;
                shared.Unfreeze(r.Hands);
            }
        }
    }

    void Toggle() {
        try {
            if (!on) {
                if (!File.Exists(Layer.Dll)) { MessageBox.Show("hand_freeze_layer.dll is missing from this folder:\n" + Layer.Dll, "Hand Freeze"); return; }
                Layer.TurnOn(); on = true;
            } else {
                countdownHands = 0; shared.Unfreeze(Hands.BOTH); Layer.TurnOff(); on = false;
            }
        } catch (Exception ex) { MessageBox.Show("Could not switch: " + ex.Message, "Hand Freeze"); }
    }

    void SetSeconds(int v) { seconds = Math.Max(0, Math.Min(MAX_SECONDS, v)); SaveSettings(); }

    static void Beep(int hz, int ms) { ThreadPool.QueueUserWorkItem(_ => { try { Console.Beep(hz, ms); } catch { } }); }

    // ---- hit testing (canvas coordinates) --------------------------------------------------------------------------
    string HitTest(Point screen) {
        float x = screen.X / (float)scale, y = screen.Y / (float)scale;
        if (Dist(x, y, SWITCH_X, SWITCH_Y) <= SWITCH_R) return "switch";
        if (new RectangleF(CANVAS_W - 30, STATUS_Y - 4, 26, 13).Contains(x, y)) return "pin";
        if (new RectangleF(118, SECONDS_Y - 1, 16, 15).Contains(x, y)) return "minus";
        if (new RectangleF(176, SECONDS_Y - 1, 16, 15).Contains(x, y)) return "plus";
        foreach (var r in Rows) {
            int cy = r.Y + ROW_H / 2 - 2;
            if (Dist(x, y, FLAKE_X, cy) <= FLAKE_R) return "freeze" + r.Hands;
            if (new RectangleF(FLAME_X - 24, cy - 28, 48, 56).Contains(x, y)) return "unfreeze" + r.Hands;
        }
        return "";
    }
    static float Dist(float x, float y, float cx, float cy) { return (float)Math.Sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy)); }

    // ---- drawing ---------------------------------------------------------------------------------------------------
    protected override void OnPaint(PaintEventArgs e) {
        using (var g = Graphics.FromImage(canvas)) {
            g.SmoothingMode = SmoothingMode.None;
            g.TextRenderingHint = TextRenderingHint.SingleBitPerPixelGridFit;   // hard-edged pixel letters
            g.PixelOffsetMode = PixelOffsetMode.Half;
            DrawBackground(g);
            DrawHeader(g);
            DrawSeconds(g);
            foreach (var r in Rows) DrawRow(g, r);
            DrawStatus(g);
        }
        e.Graphics.InterpolationMode = InterpolationMode.NearestNeighbor;
        e.Graphics.PixelOffsetMode = PixelOffsetMode.Half;
        e.Graphics.DrawImage(canvas, new Rectangle(0, 0, CANVAS_W * scale, CANVAS_H * scale));
    }

    void DrawBackground(Graphics g) {
        int frame = (int)((DateTime.Now - started).TotalMilliseconds / FRAME_MS);
        g.DrawImage(summer[frame % summer.Count], 0, 0, CANVAS_W, CANVAS_H);
        if (fade > 0) {   // the winter scene fades in over the summer one
            var cm = new ColorMatrix { Matrix33 = fade };
            using (var ia = new ImageAttributes()) {
                ia.SetColorMatrix(cm);
                g.DrawImage(winter[frame % winter.Count], new Rectangle(0, 0, CANVAS_W, CANVAS_H), 0, 0, CANVAS_W, CANVAS_H, GraphicsUnit.Pixel, ia);
            }
        }
    }

    static Color Mix(Color a, Color b, float t) {
        return Color.FromArgb((int)(a.R + (b.R - a.R) * t), (int)(a.G + (b.G - a.G) * t), (int)(a.B + (b.B - a.B) * t));
    }
    static Color Lighter(Color c, float t) { return Mix(c, Color.White, t); }
    static Color Grey(Color c) { int v = (c.R + c.G + c.B) / 3; return Mix(Color.FromArgb(v, v, v), Color.FromArgb(120, 120, 125), 0.4f); }

    const float SMALL = 8, BIG = 16;   // Silkscreen's own pixel sizes; anything in between blurs the letters

    Font F(float px) { return new Font(face, px, FontStyle.Regular, GraphicsUnit.Pixel); }

    // text with a one-pixel dark outline, so it reads on any background
    void Say(Graphics g, string text, float px, float x, float y, Color color, bool centre = false) {
        using (var f = F(px))
        using (var b = new SolidBrush(color))
        using (var o = new SolidBrush(Ink)) {
            if (centre) x -= g.MeasureString(text, f, PointF.Empty, StringFormat.GenericTypographic).Width / 2;
            var fmt = StringFormat.GenericTypographic;
            for (int dx = -1; dx <= 1; dx++) for (int dy = -1; dy <= 1; dy++) if (dx != 0 || dy != 0) g.DrawString(text, f, o, x + dx, y + dy, fmt);
            g.DrawString(text, f, b, x, y, fmt);
        }
    }

    void Panel(Graphics g, int x, int y, int w, int h) {
        using (var b = new SolidBrush(Color.FromArgb(120, Ink))) g.FillRectangle(b, x, y, w, h);
        using (var p = new Pen(Color.FromArgb(160, Paper))) g.DrawRectangle(p, x, y, w - 1, h - 1);
    }

    void DrawHeader(Graphics g) {
        Panel(g, 4, 4, CANVAS_W - 8, 62);
        Say(g, "HAND", BIG, 12, 9, Paper);
        Say(g, "FREEZE", BIG, 12, 26, Lighter(Ice, 0.3f));
        Say(g, on ? "On: start or restart the game," : "Off: no game is touched.", SMALL, 12, 47, Paper);
        Say(g, on ? "then freeze any time." : "Switch on before the game starts.", SMALL, 12, 56, Paper);
        // the round switch
        Color c = Mix(Red, Green, fade);
        bool hot = hover == "switch", down = pressed == "switch";
        int r = SWITCH_R, cx = SWITCH_X, cy = SWITCH_Y + (down ? 1 : 0);
        using (var b = new SolidBrush(Ink)) g.FillEllipse(b, cx - r - 2, cy - r - 2, 2 * r + 4, 2 * r + 4);
        using (var b = new SolidBrush(Mix(c, Ink, 0.35f))) g.FillEllipse(b, cx - r, cy - r + 2, 2 * r, 2 * r);   // rim
        using (var b = new SolidBrush(hot ? Lighter(c, 0.15f) : c)) g.FillEllipse(b, cx - r, cy - r, 2 * r, 2 * r - 2);
        using (var b = new SolidBrush(Lighter(c, 0.45f))) g.FillEllipse(b, cx - r + 5, cy - r + 3, r - 2, r / 2);     // shine
        Say(g, fade >= 0.5f ? "ON" : "OFF", BIG, cx, cy - 8, Paper, true);
    }

    void DrawSeconds(Graphics g) {
        Panel(g, 4, SECONDS_Y - 4, CANVAS_W - 8, 22);
        Say(g, "SECONDS TO FREEZE", SMALL, 12, SECONDS_Y + 2, on ? Paper : Grey(Paper));
        DrawArrowBox(g, 118, "minus", "<");
        using (var b = new SolidBrush(Color.FromArgb(200, Ink))) g.FillRectangle(b, 136, SECONDS_Y - 1, 38, 15);
        Say(g, seconds.ToString(), BIG, 155, SECONDS_Y - 2, on ? Paper : Grey(Paper), true);
        DrawArrowBox(g, 176, "plus", ">");
    }

    void DrawArrowBox(Graphics g, int x, string id, string arrow) {
        Color c = !on ? Grey(IceDeep) : hover == id ? Lighter(IceDeep, 0.25f) : IceDeep;
        int y = SECONDS_Y - 1 + (pressed == id ? 1 : 0);
        using (var b = new SolidBrush(c)) g.FillRectangle(b, x, y, 16, 15);
        using (var p = new Pen(Ink)) g.DrawRectangle(p, x, y, 15, 14);
        Say(g, arrow, BIG, x + 8, y - 1, Paper, true);
    }

    void DrawRow(Graphics g, Row r) {
        int cy = r.Y + ROW_H / 2 - 2;
        bool frozen = (shared.Frozen & r.Hands) == r.Hands;
        bool counting = countdownHands == r.Hands;
        Panel(g, 4, r.Y, CANVAS_W - 8, ROW_H - 4);
        if (frozen) using (var b = new SolidBrush(Color.FromArgb(90, Ice))) g.FillRectangle(b, 5, r.Y + 1, CANVAS_W - 10, ROW_H - 6);
        Color word = frozen ? Ice : (on ? Paper : Grey(Paper));
        Say(g, r.Label, BIG, LABEL_X, cy - 24, word);   // two lines: LEFT / HAND, so the words stay big and clear
        Say(g, r.Noun, BIG, LABEL_X, cy - 9, word);
        Say(g, frozen ? "FROZEN" : counting ? "HOLD STILL" : "", SMALL, LABEL_X, cy + 10, frozen ? Ice : FlameIn);
        string flakeId = "freeze" + r.Hands, flameId = "unfreeze" + r.Hands;
        DrawSnowflake(g, FLAKE_X, cy + (pressed == flakeId ? 1 : 0), hover == flakeId);
        string inside = counting ? Math.Max(1, (int)Math.Ceiling((countdownEnd - DateTime.Now).TotalSeconds)).ToString() : "FREEZE";
        Say(g, inside, counting ? BIG : SMALL, FLAKE_X, cy - (counting ? 8 : 4) + (pressed == flakeId ? 1 : 0), Paper, true);
        DrawFlame(g, FLAME_X, cy + (pressed == flameId ? 1 : 0), hover == flameId);
        int down = pressed == flameId ? 1 : 0;   // two lines, UN- over FREEZE: fits the flame's shape (Tefa, 2026-10-13)
        Say(g, "UN-", SMALL, FLAME_X, cy + 3 + down, Paper, true);
        Say(g, "FREEZE", SMALL, FLAME_X, cy + 12 + down, Paper, true);
    }

    void DrawSnowflake(Graphics g, int cx, int cy, bool hot) {
        Color body = !on ? Grey(Ice) : hot ? Lighter(Ice, 0.4f) : Ice, deep = !on ? Grey(IceDeep) : IceDeep;
        for (int pass = 0; pass < 2; pass++) {   // a dark outline pass, then the ice on top
            using (var pen = new Pen(pass == 0 ? Ink : body, pass == 0 ? 6 : 3) { StartCap = LineCap.Round, EndCap = LineCap.Round }) {
                for (int k = 0; k < 6; k++) {
                    double a = k * Math.PI / 3;   // arms left and right, so the flakes of neighbouring rows never touch
                    float ex = cx + (float)(FLAKE_R * Math.Cos(a)), ey = cy + (float)(FLAKE_R * Math.Sin(a));
                    g.DrawLine(pen, cx, cy, ex, ey);
                    // two pairs of side branches leaning outwards, a long pair and a short one near the tip: a real flake
                    for (int pair = 0; pair < 2; pair++) {
                        double at = pair == 0 ? 0.66 : 0.86, len = pair == 0 ? 8.0 : 4.5;
                        float mx = cx + (float)(FLAKE_R * at * Math.Cos(a)), my = cy + (float)(FLAKE_R * at * Math.Sin(a));
                        foreach (int side in new[] { -1, 1 }) {
                            double b = a + side * Math.PI / 3;
                            g.DrawLine(pen, mx, my, mx + (float)(len * Math.Cos(b)), my + (float)(len * Math.Sin(b)));
                        }
                    }
                }
            }
            int r = pass == 0 ? 20 : 18;   // wide enough for the word FREEZE
            using (var b = new SolidBrush(pass == 0 ? Ink : deep)) g.FillEllipse(b, cx - r, cy - r, 2 * r, 2 * r);
        }
        using (var b = new SolidBrush(Lighter(deep, 0.25f))) g.FillEllipse(b, cx - 14, cy - 16, 24, 10);   // a little shine
    }

    void DrawFlame(Graphics g, int cx, int cy, bool hot) {
        Color outC = !on ? Grey(FlameOut) : hot ? Lighter(FlameOut, 0.2f) : FlameOut;
        Color inC = !on ? Grey(FlameIn) : hot ? Lighter(FlameIn, 0.2f) : FlameIn;
        Color edge = !on ? Grey(FlameEdge) : FlameEdge;
        float flick = on ? (float)Math.Sin((DateTime.Now - started).TotalMilliseconds / 180.0) : 0;
        using (var outer = FlamePath(cx, cy + 2, 23, 26, flick))
        using (var inner = FlamePath(cx, cy + 8, 14, 17, -flick)) {
            using (var p = new Pen(edge, 3)) g.DrawPath(p, outer);
            using (var b = new SolidBrush(outC)) g.FillPath(b, outer);
            using (var b = new SolidBrush(inC)) g.FillPath(b, inner);
        }
        using (var b = new SolidBrush(Color.FromArgb(150, edge))) g.FillRectangle(b, cx - 20, cy + 2, 40, 19);   // a band for the two words
    }

    // a flame: round at the bottom, three tongues at the top, the middle one tallest; `flick` sways the tips
    static GraphicsPath FlamePath(float cx, float cy, float w, float h, float flick) {
        var p = new GraphicsPath();
        float bottom = cy + h * 0.75f, top = cy - h;
        p.AddBezier(cx, bottom, cx - w * 1.1f, bottom, cx - w, cy, cx - w * 0.7f + flick, cy - h * 0.45f);
        p.AddBezier(cx - w * 0.7f + flick, cy - h * 0.45f, cx - w * 0.45f, cy - h * 0.1f, cx - w * 0.35f, cy - h * 0.2f, cx - w * 0.3f + flick, cy - h * 0.65f);
        p.AddBezier(cx - w * 0.3f + flick, cy - h * 0.65f, cx - w * 0.15f, cy - h * 0.35f, cx - w * 0.1f, cy - h * 0.6f, cx + flick * 1.5f, top);
        p.AddBezier(cx + flick * 1.5f, top, cx + w * 0.15f, cy - h * 0.6f, cx + w * 0.2f, cy - h * 0.35f, cx + w * 0.35f + flick, cy - h * 0.6f);
        p.AddBezier(cx + w * 0.35f + flick, cy - h * 0.6f, cx + w * 0.4f, cy - h * 0.2f, cx + w * 0.5f, cy - h * 0.1f, cx + w * 0.7f + flick, cy - h * 0.4f);
        p.AddBezier(cx + w * 0.7f + flick, cy - h * 0.4f, cx + w, cy, cx + w * 1.1f, bottom, cx, bottom);
        p.CloseFigure();
        return p;
    }

    void DrawStatus(Graphics g) {
        Panel(g, 4, STATUS_Y - 6, CANVAS_W - 8, 18);
        string text;
        if (!on) text = "Switched off.";
        else if (!shared.GameConnected) text = "No OpenXR game connected yet.";
        else {
            string hands = (shared.LeftSpaces > 0 ? "L" : "") + (shared.RightSpaces > 0 ? "R" : "");
            text = "Connected: " + shared.GameName + (hands.Length > 0 ? "  (" + hands + ")" : "");
        }
        Say(g, text, 8, 10, STATUS_Y - 3, Paper);
        Color pc = pinned ? Green : (hover == "pin" ? Lighter(IceDeep, 0.25f) : IceDeep);
        using (var b = new SolidBrush(pc)) g.FillRectangle(b, CANVAS_W - 30, STATUS_Y - 4, 26, 13);
        using (var p = new Pen(Ink)) g.DrawRectangle(p, CANVAS_W - 30, STATUS_Y - 4, 25, 12);
        Say(g, "TOP", 8, CANVAS_W - 17, STATUS_Y - 3, Paper, true);
    }
}
