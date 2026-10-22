package com.nanaveone.fable2;

import android.os.Bundle;
import android.system.Os;
import android.util.Log;
import java.io.File;
import org.libsdl.app.SDLActivity;

/**
 * Android entrypoint for the Fable II ReXGlue port.
 *
 * This is an actual SDL activity targeting Fable II, NOT the Burnout activity.
 * Native libraries must be produced by the Fable II Android cross-build:
 * libc++_shared.so, librexruntime.so, libfable2.so.
 * The native renderer and game-specific hooks are NOT implemented by this file.
 */
public final class Fable2Activity extends SDLActivity {
    private File gameRoot;

    @Override
    protected void onCreate(Bundle state) {
        File external = getExternalFilesDir(null);
        if (external == null) {
            external = getFilesDir();
        }
        gameRoot = new File(external, "game");
        if (!gameRoot.isDirectory()) {
            Log.w("Fable2Port", "Game directory not installed: " + gameRoot);
        }
        try {
            Os.setenv("FABLE2_GAME_ROOT", gameRoot.getAbsolutePath(), true);
        } catch (Exception error) {
            Log.w("Fable2Port", "Unable to set FABLE2_GAME_ROOT", error);
        }
        super.onCreate(state);
    }

    @Override
    protected String[] getLibraries() {
        // Mirrors the load order of Xerenge's Android SDLActivity. The native
        // game target must export SDL_main and be built as libfable2.so.
        return new String[] {"c++_shared", "rexruntime", "fable2"};
    }

    @Override
    protected String[] getArguments() {
        File root = gameRoot;
        if (root == null) {
            File external = getExternalFilesDir(null);
            root = new File(external != null ? external : getFilesDir(), "game");
        }
        return new String[] {"--game_data_root=" + root.getAbsolutePath()};
    }
}
