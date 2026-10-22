package com.nanaveone.fable2;

import java.io.File;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

/** Entirely synthetic GDFX fixture: no Fable II game files. */
public final class Fable2IsoExtractorTest {
    static final int SECTOR = 2048;
    static int tests = 0;

    static void check(boolean value, String why) {
        tests++;
        if (!value) throw new AssertionError(why);
    }

    static void u32(byte[] out, int index, int v) {
        for (int k = 0; k < 4; k++) out[index + k] = (byte) (v >>> (k * 8));
    }

    static int entry(byte[] out, int pos, String name, int sector, int size, boolean directory) {
        byte[] raw = name.getBytes(java.nio.charset.StandardCharsets.US_ASCII);
        u32(out, pos + 4, sector);
        u32(out, pos + 8, size);
        out[pos + 12] = (byte) (directory ? 0x10 : 0x80);
        out[pos + 13] = (byte) raw.length;
        System.arraycopy(raw, 0, out, pos + 14, raw.length);
        return pos + ((14 + raw.length + 3) & ~3);
    }

    static byte[] fixture() {
        byte[] iso = new byte[0x10000 + 0x4000];
        int header = 0x10000;
        System.arraycopy(Fable2IsoExtractor.MAGIC, 0, iso, header, Fable2IsoExtractor.MAGIC.length);
        u32(iso, header + 20, 4);
        u32(iso, header + 24, SECTOR);
        int rootStart = 4 * SECTOR;
        int pos = entry(iso, rootStart, "default.xex", 20, 4, false);
        pos = entry(iso, pos, "data", 5, SECTOR * 2, true);
        pos = entry(iso, pos, "nxeart", 21, 8, false);
        Arrays.fill(iso, pos, rootStart + SECTOR, (byte) 0xFF);
        int dataStart = 5 * SECTOR;
        pos = entry(iso, dataStart, "gold_version.txt", 22, 4, false);
        Arrays.fill(iso, pos, dataStart + SECTOR, (byte) 0xFF); // GDFX sector-batch boundary
        pos = entry(iso, dataStart + SECTOR, "startup.vfsconfig", 23, 5, false);
        Arrays.fill(iso, pos, dataStart + 2 * SECTOR, (byte) 0xFF);
        System.arraycopy(new byte[]{'X','E','X','2'}, 0, iso, 20 * SECTOR, 4);
        System.arraycopy(new byte[]{'N','X','E','A','R','T','0','0'}, 0, iso, 21 * SECTOR, 8);
        System.arraycopy(new byte[]{'G','O','T','Y'}, 0, iso, 22 * SECTOR, 4);
        System.arraycopy(new byte[]{'c','f','g','x','y'}, 0, iso, 23 * SECTOR, 5);
        return iso;
    }

    static void expectIOException(byte[] source, String hint) throws Exception {
        Path temp = Files.createTempFile("fake-gdfx", ".iso");
        try {
            Files.write(temp, source);
            try (RandomAccessFile input = new RandomAccessFile(temp.toFile(), "r")) {
                boolean failed = false;
                try { new Fable2IsoExtractor(input.getChannel()); }
                catch (IOException err) { failed = true; }
                check(failed, hint);
            }
        } finally { Files.deleteIfExists(temp); }
    }

    static void testExtraction() throws Exception {
        Path tmp = Files.createTempDirectory("fable-iso-test");
        try {
            Path iso = tmp.resolve("test.iso");
            Files.write(iso, fixture());
            try (RandomAccessFile file = new RandomAccessFile(iso.toFile(), "r")) {
                Fable2IsoExtractor disc = new Fable2IsoExtractor(file.getChannel());
                check(disc.getRoot().size() == 3, "expected root entries");
                File staging = tmp.resolve("pending").toFile();
                disc.extractFile(disc.rootFile("default.xex"), new File(staging,"default.xex"), null);
                disc.extractDataDirectory(disc.rootDirectory("data"), staging, null);
                check(Arrays.equals(Files.readAllBytes(tmp.resolve("pending/default.xex")),
                        new byte[]{'X','E','X','2'}), "XEX extraction");
                check(Arrays.equals(Files.readAllBytes(tmp.resolve("pending/data/gold_version.txt")),
                        new byte[]{'G','O','T','Y'}), "first directory batch");
                check(Arrays.equals(Files.readAllBytes(tmp.resolve("pending/data/startup.vfsconfig")),
                        new byte[]{'c','f','g','x','y'}), "second directory batch");
                check(!Files.exists(tmp.resolve("pending/nxeart")), "system content not copied");
                boolean missing = false;
                try { disc.rootDirectory("update"); }
                catch (IOException e) { missing = true; }
                check(missing, "unknown directory must be rejected");
            }
        } finally {
            try (java.util.stream.Stream<Path> paths = Files.walk(tmp)) {
                paths.sorted(java.util.Comparator.reverseOrder()).forEach(p -> p.toFile().delete());
            }
        }
    }

    static void testHeaderAcrossScanChunk() throws Exception {
        byte[] base = fixture();
        int header = (4 * 1024 * 1024) - 8; // Magic crosses the 4 MiB scan window.
        int relocatedBase = header - 0x10000;
        byte[] iso = new byte[header + 8192];
        System.arraycopy(base, 0, iso, relocatedBase, 25 * SECTOR);
        System.arraycopy(Fable2IsoExtractor.MAGIC, 0, iso, header, Fable2IsoExtractor.MAGIC.length);
        u32(iso, header + 20, 4);
        u32(iso, header + 24, SECTOR);
        Path file = Files.createTempFile("gdfx-scan-seam", ".iso");
        try {
            Files.write(file, iso);
            try (RandomAccessFile input = new RandomAccessFile(file.toFile(), "r")) {
                Fable2IsoExtractor reader = new Fable2IsoExtractor(input.getChannel());
                check(reader.rootFile("default.xex").size == 4, "scan window boundary");
            }
        } finally { Files.deleteIfExists(file); }
    }

    static void testCorruption() throws Exception {
        byte[] noMagic = fixture();
        Arrays.fill(noMagic, 0x10000, 0x10000 + Fable2IsoExtractor.MAGIC.length, (byte) 0);
        expectIOException(noMagic, "missing signature rejected");
        byte[] traversal = fixture();
        byte[] invalid = new byte[]{'.', '.'};
        System.arraycopy(invalid, 0, traversal, 4 * SECTOR + 14, invalid.length);
        traversal[4 * SECTOR + 13] = 2;
        expectIOException(traversal, "path traversal rejected");
        byte[] overflow = fixture();
        u32(overflow, 4 * SECTOR + 8, Integer.MAX_VALUE);
        expectIOException(overflow, "out-of-bounds extent rejected");
    }

    public static void main(String[] args) throws Exception {
        testExtraction();
        testCorruption();
        testHeaderAcrossScanChunk();
        System.out.println("PASS: " + tests + " GDFX extraction/security assertions");
    }
}
