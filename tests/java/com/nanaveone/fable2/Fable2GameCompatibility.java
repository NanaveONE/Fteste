package com.nanaveone.fable2;
import java.io.*;
import java.util.Arrays;
/** Synthetic-only substitute. Production uses the existing SHA-256 catalogue. */
final class Fable2GameCompatibility {
    static final class Profile { String id = "synthetic-goty"; }
    static Profile checkXex(InputStream xex) throws IOException {
        if (!Arrays.equals(xex.readAllBytes(), new byte[]{'X','E','X','2'}))
            throw new IOException("wrong synthetic xex");
        return new Profile();
    }
    static void checkData(File root, Profile profile) throws IOException {
        if (!new File(root,"data/gold_version.txt").isFile() ||
            !new File(root,"data/startup.vfsconfig").isFile())
            throw new IOException("missing synthetic data");
    }
}
