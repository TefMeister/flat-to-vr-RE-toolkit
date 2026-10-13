// HandFreeze.cs -- the Hand Freeze desktop app: start-up, the shared switch, and the OpenXR registration. The window
// itself is FreezeUi.cs.
//
// Tefa, 2026-10-13: "a small program with an icon on the desktop, where i can just switch this on and off, a universal
// one for OpenXR, with a choice of seconds till the freeze and a button to unfreeze controllers". Then, the same day:
// summer background when off, winter when on, a round red/green switch, a snowflake FREEZE and a flame UNFREEZE button,
// rows for LEFT, RIGHT and BOTH, an Optima-like font, all pixelated.
//
// ON/OFF registers the OpenXR layer (hand_freeze_layer.dll, next to this exe) for every OpenXR game of this Windows user
// (HKCU, no admin). A game picks it up when it starts, so the switch has to be on before the game starts; the window can
// be opened and closed at any time. FREEZE counts down, then tells the layer which hands to hold; UNFREEZE lets them go.
// Closing the window always unfreezes. The switch is the shared-memory block of ../shared.h (offsets below match it).
using System;
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
            Application.Run(new FreezeUi());
        }
    }
}

// which hands: the bits of the shared block's `frozen`
static class Hands { public const int LEFT = 1, RIGHT = 2, BOTH = 3; }

class Shared : IDisposable {
    const string NAME = @"Local\FlatToVR_HandFreeze_v2";
    const uint MAGIC = 0x5A465248, VERSION = 2;
    const int SIZE = 180, FROZEN = 8, GEN_LEFT = 12, HEARTBEAT = 16, CONTROLLERS = 28, GAME_NAME = 40,
              GEN_RIGHT = 168, LEFT_SPACES = 172, RIGHT_SPACES = 176;
    const ulong CONNECTED_WITHIN_MS = 3000;   // a game counts as connected if the layer was heard from this recently
    readonly MemoryMappedFile file;
    readonly MemoryMappedViewAccessor view;

    [DllImport("kernel32.dll")] static extern ulong GetTickCount64();

    public Shared() {
        file = MemoryMappedFile.CreateOrOpen(NAME, SIZE);
        view = file.CreateViewAccessor(0, SIZE);
        if (view.ReadUInt32(0) != MAGIC) { view.Write(4, VERSION); view.Write(0, MAGIC); }
    }
    public int Frozen { get { return view.ReadInt32(FROZEN); } }
    public void Freeze(int hands) {
        if ((hands & Hands.LEFT) != 0) view.Write(GEN_LEFT, view.ReadInt32(GEN_LEFT) + 1);   // fresh poses for these hands
        if ((hands & Hands.RIGHT) != 0) view.Write(GEN_RIGHT, view.ReadInt32(GEN_RIGHT) + 1);
        view.Write(FROZEN, Frozen | hands);
    }
    public void Unfreeze(int hands) { view.Write(FROZEN, Frozen & ~hands); }
    public int Controllers { get { return view.ReadInt32(CONTROLLERS); } }
    public int LeftSpaces { get { return view.ReadInt32(LEFT_SPACES); } }
    public int RightSpaces { get { return view.ReadInt32(RIGHT_SPACES); } }
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
            "    \"library_path\": \"" + Dll.Replace("\\", "\\\\") + "\",\n    \"api_version\": \"1.0\",\n    \"implementation_version\": \"2\",\n" +
            "    \"description\": \"Hand Freeze: holds the controllers still on request, from the Hand Freeze app\",\n" +
            "    \"disable_environment\": \"DISABLE_HAND_FREEZE_LAYER\"\n  }\n}\n";
        File.WriteAllText(Manifest, json);
        using (var k = Registry.CurrentUser.CreateSubKey(KEY)) k.SetValue(Manifest, 0, RegistryValueKind.DWord);
    }
    public static void TurnOff() {
        using (var k = Registry.CurrentUser.OpenSubKey(KEY, true)) if (k != null) k.DeleteValue(Manifest, false);
    }
}
