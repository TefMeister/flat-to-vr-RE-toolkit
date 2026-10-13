// HandFreeze.cs -- the Hand Freeze desktop app (Tefa, 2026-10-13: "a small program with an icon on the desktop, where i
// can just switch this on and off, a universal one for OpenXR, with a choice of seconds till the freeze and a button to
// unfreeze controllers").
//
// ON/OFF registers the OpenXR layer (hand_freeze_layer.dll, next to this exe) for every OpenXR game of this Windows user
// (HKCU, no admin). A game picks it up when it starts, so switching on affects games started afterwards.
// FREEZE counts down the chosen seconds with a beep each second, then tells the layer to hold both controllers where
// they are; UNFREEZE lets them follow again. Closing the app always unfreezes. The switch is the shared-memory block
// described in ../shared.h (byte offsets below must match it).
using System;
using System.Drawing;
using System.IO;
using System.IO.MemoryMappedFiles;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

static class Program {
    [STAThread]
    static void Main() {
        bool first;
        using (var one = new Mutex(true, "FlatToVR_HandFreeze_App", out first)) {
            if (!first) { MessageBox.Show("Hand Freeze is already open.", "Hand Freeze"); return; }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }
}

class Shared : IDisposable {
    const string NAME = @"Local\FlatToVR_HandFreeze_v1";
    const uint MAGIC = 0x5A465248, VERSION = 1;
    const int SIZE = 168, FROZEN = 8, GENERATION = 12, HEARTBEAT = 16, CONTROLLERS = 28, GAME_NAME = 40;
    const ulong CONNECTED_WITHIN_MS = 3000;   // a game counts as connected if the layer was heard from this recently
    readonly MemoryMappedFile file;
    readonly MemoryMappedViewAccessor view;

    [DllImport("kernel32.dll")] static extern ulong GetTickCount64();

    public Shared() {
        file = MemoryMappedFile.CreateOrOpen(NAME, SIZE);
        view = file.CreateViewAccessor(0, SIZE);
        if (view.ReadUInt32(0) != MAGIC) { view.Write(4, VERSION); view.Write(0, MAGIC); }
    }
    public bool Frozen { get { return view.ReadInt32(FROZEN) != 0; } }
    public void Freeze() { view.Write(GENERATION, view.ReadInt32(GENERATION) + 1); view.Write(FROZEN, 1); }
    public void Unfreeze() { view.Write(FROZEN, 0); }
    public int Controllers { get { return view.ReadInt32(CONTROLLERS); } }
    public bool GameConnected { get { ulong hb = view.ReadUInt64(HEARTBEAT); return hb != 0 && GetTickCount64() - hb < CONNECTED_WITHIN_MS; } }
    public string GameName {
        get {
            var chars = new char[64];
            view.ReadArray(GAME_NAME, chars, 0, 64);
            int n = Array.IndexOf(chars, '\0');
            return new string(chars, 0, n < 0 ? 64 : n);
        }
    }
    public void Dispose() { view.Dispose(); file.Dispose(); }
}

static class Layer {
    const string KEY = @"Software\Khronos\OpenXR\1\ApiLayers\Implicit";
    public const string LAYER_NAME = "XR_APILAYER_FLATTOVR_hand_freeze";
    static string Dir { get { return AppDomain.CurrentDomain.BaseDirectory; } }
    public static string Dll { get { return Path.Combine(Dir, "hand_freeze_layer.dll"); } }
    public static string Manifest { get { return Path.Combine(Dir, "hand_freeze_layer.json"); } }

    public static bool IsOn() {
        using (var k = Registry.CurrentUser.OpenSubKey(KEY)) {
            object v = k == null ? null : k.GetValue(Manifest);
            return v is int && (int)v == 0;
        }
    }
    public static void TurnOn() {
        // the manifest names the DLL by its full path, so it works wherever the folder was put
        string json = "{\n  \"file_format_version\": \"1.0.0\",\n  \"api_layer\": {\n    \"name\": \"" + LAYER_NAME + "\",\n" +
            "    \"library_path\": \"" + Dll.Replace("\\", "\\\\") + "\",\n    \"api_version\": \"1.0\",\n    \"implementation_version\": \"1\",\n" +
            "    \"description\": \"Hand Freeze: holds both controllers still on request, from the Hand Freeze app\",\n" +
            "    \"disable_environment\": \"DISABLE_HAND_FREEZE_LAYER\"\n  }\n}\n";
        File.WriteAllText(Manifest, json);
        using (var k = Registry.CurrentUser.CreateSubKey(KEY)) k.SetValue(Manifest, 0, RegistryValueKind.DWord);
    }
    public static void TurnOff() {
        using (var k = Registry.CurrentUser.OpenSubKey(KEY, true)) if (k != null) k.DeleteValue(Manifest, false);
    }
}

class MainForm : Form {
    readonly Shared shared = new Shared();
    readonly CheckBox onOff = new CheckBox();
    readonly NumericUpDown seconds = new NumericUpDown();
    readonly Button freeze = new Button(), unfreeze = new Button();
    readonly Label big = new Label(), status = new Label(), hint = new Label();
    readonly CheckBox onTop = new CheckBox();
    readonly System.Windows.Forms.Timer tick = new System.Windows.Forms.Timer();
    const int DEFAULT_SECONDS = 10, MAX_SECONDS = 60;                     // Tefa asked for 10 s; a minute is plenty
    const int TICK_HZ = 880, TICK_MS = 70, FROZEN_HZ = 1320, FROZEN_MS = 350; // the countdown beeps and the final one
    DateTime countdownEnd = DateTime.MinValue;
    int lastBeep = -1;
    readonly string settingsFile = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "settings.txt");

    static readonly Color Back = Color.FromArgb(30, 32, 38), PanelC = Color.FromArgb(44, 47, 56), Fore = Color.FromArgb(235, 235, 240);
    static readonly Color Green = Color.FromArgb(70, 170, 110), Red = Color.FromArgb(200, 80, 80), Blue = Color.FromArgb(70, 130, 210), Dim = Color.FromArgb(160, 165, 175);

    public MainForm() {
        Text = "Hand Freeze";
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
        Font = new Font("Segoe UI", 11f);
        BackColor = Back; ForeColor = Fore;
        FormBorderStyle = FormBorderStyle.FixedSingle; MaximizeBox = false;
        AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(420, 400);

        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(16), ColumnCount = 2, RowCount = 7 };
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50)); layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
        Controls.Add(layout);

        onOff.Appearance = Appearance.Button; onOff.FlatStyle = FlatStyle.Flat; onOff.Dock = DockStyle.Fill; onOff.Height = 48;
        onOff.FlatAppearance.CheckedBackColor = Green; onOff.FlatAppearance.BorderSize = 0; onOff.ForeColor = Color.White;
        onOff.TextAlign = ContentAlignment.MiddleCenter; onOff.Font = new Font("Segoe UI", 13f, FontStyle.Bold);
        onOff.Checked = Layer.IsOn();
        onOff.CheckedChanged += OnSwitch;
        layout.Controls.Add(onOff, 0, 0); layout.SetColumnSpan(onOff, 2);

        hint.Dock = DockStyle.Fill; hint.ForeColor = Dim; hint.Font = new Font("Segoe UI", 9.5f); hint.Height = 40;
        layout.Controls.Add(hint, 0, 1); layout.SetColumnSpan(hint, 2);

        var secLabel = new Label { Text = "Seconds before it freezes:", Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft };
        seconds.Minimum = 0; seconds.Maximum = MAX_SECONDS; seconds.Value = LoadSeconds(); seconds.Dock = DockStyle.Fill;
        seconds.BackColor = PanelC; seconds.ForeColor = Fore; seconds.TextAlign = HorizontalAlignment.Center;
        seconds.ValueChanged += (s, e) => SaveSeconds();
        layout.Controls.Add(secLabel, 0, 2); layout.Controls.Add(seconds, 1, 2);

        Style(freeze, "Freeze controllers", Blue); freeze.Click += (s, e) => StartCountdown();
        Style(unfreeze, "Unfreeze", Red); unfreeze.Click += (s, e) => Unfreeze();
        layout.Controls.Add(freeze, 0, 3); layout.Controls.Add(unfreeze, 1, 3);

        big.Dock = DockStyle.Fill; big.TextAlign = ContentAlignment.MiddleCenter; big.Font = new Font("Segoe UI", 18f, FontStyle.Bold); big.Height = 64;
        layout.Controls.Add(big, 0, 4); layout.SetColumnSpan(big, 2);

        status.Dock = DockStyle.Fill; status.ForeColor = Dim; status.Font = new Font("Segoe UI", 9.5f); status.Height = 44;
        layout.Controls.Add(status, 0, 5); layout.SetColumnSpan(status, 2);

        onTop.Text = "Keep this window on top"; onTop.Dock = DockStyle.Fill; onTop.CheckedChanged += (s, e) => TopMost = onTop.Checked;
        layout.Controls.Add(onTop, 0, 6); layout.SetColumnSpan(onTop, 2);

        tick.Interval = 100; tick.Tick += (s, e) => Refresh2(); tick.Start();
        FormClosing += (s, e) => { shared.Unfreeze(); shared.Dispose(); };
        Refresh2();
    }

    static void Style(Button b, string text, Color c) {
        b.Text = text; b.Dock = DockStyle.Fill; b.Height = 52; b.FlatStyle = FlatStyle.Flat; b.BackColor = c; b.ForeColor = Color.White;
        b.FlatAppearance.BorderSize = 0; b.Font = new Font("Segoe UI", 11.5f, FontStyle.Bold);
    }

    void OnSwitch(object s, EventArgs e) {
        try {
            if (onOff.Checked) {
                if (!File.Exists(Layer.Dll)) { MessageBox.Show("hand_freeze_layer.dll is missing from this folder:\n" + Layer.Dll, "Hand Freeze"); onOff.Checked = false; return; }
                Layer.TurnOn();
            } else { Unfreeze(); Layer.TurnOff(); }
        } catch (Exception ex) { MessageBox.Show("Could not switch: " + ex.Message, "Hand Freeze"); }
        Refresh2();
    }

    void StartCountdown() {
        if (!onOff.Checked) return;
        shared.Unfreeze();
        countdownEnd = DateTime.Now.AddSeconds((double)seconds.Value);
        lastBeep = -1;
        Refresh2();
    }

    void Unfreeze() { countdownEnd = DateTime.MinValue; shared.Unfreeze(); Refresh2(); }

    void Refresh2() {
        bool on = onOff.Checked;
        onOff.Text = on ? "Hand Freeze is ON" : "Hand Freeze is OFF";
        onOff.BackColor = on ? Green : PanelC;
        hint.Text = on ? "Games started from now on can be frozen. A game that was already running needs a restart."
                       : "Switch on, then start the game. Nothing in any game is changed while it is off.";
        freeze.Enabled = on; seconds.Enabled = on;

        if (countdownEnd != DateTime.MinValue) {
            double left = (countdownEnd - DateTime.Now).TotalSeconds;
            if (left <= 0) {
                countdownEnd = DateTime.MinValue;
                shared.Freeze();
                Beep(FROZEN_HZ, FROZEN_MS);
            } else {
                int whole = (int)Math.Ceiling(left);
                if (whole != lastBeep) { lastBeep = whole; Beep(TICK_HZ, TICK_MS); }
                big.Text = "Hold still... freezing in " + whole;
                big.ForeColor = Blue;
            }
        }
        if (countdownEnd == DateTime.MinValue) {
            if (shared.Frozen) { big.Text = "CONTROLLERS FROZEN"; big.ForeColor = Color.FromArgb(120, 190, 255); }
            else { big.Text = "Controllers move normally"; big.ForeColor = Dim; }
        }

        if (!on) status.Text = "";
        else if (shared.GameConnected) status.Text = "Connected to " + shared.GameName + " (" + shared.Controllers + " controller poses seen).";
        else status.Text = "No OpenXR game with Hand Freeze is running right now.";
    }

    static void Beep(int hz, int ms) { ThreadPool.QueueUserWorkItem(_ => { try { Console.Beep(hz, ms); } catch { } }); }

    decimal LoadSeconds() {
        try { decimal v; if (decimal.TryParse(File.ReadAllText(settingsFile).Trim(), out v) && v >= 0 && v <= MAX_SECONDS) return v; } catch { }
        return DEFAULT_SECONDS;
    }
    void SaveSeconds() { try { File.WriteAllText(settingsFile, seconds.Value.ToString()); } catch { } }
}
