package com.nanaveone.fable2;

import android.content.ContentResolver;
import android.net.Uri;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

/** Android installation transaction exercised with host-only SAF stubs. */
public final class Fable2IsoInstallerTest {
    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("fable2-installer-test");
        try {
            Path iso = temp.resolve("own-disc.iso");
            Files.write(iso, Fable2IsoExtractorTest.fixture());
            Path game = temp.resolve("files/game");
            ContentResolver resolver = new ContentResolver();
            Fable2IsoInstaller.install(resolver, new Uri(iso.toString()), game.toFile(), message -> {});
            Fable2IsoExtractorTest.check(Files.isRegularFile(game.resolve(".import-complete")),
                    "installed only after validation");
            Fable2IsoExtractorTest.check(Files.isRegularFile(game.resolve("data/gold_version.txt")),
                    "data installed");
            Fable2IsoExtractorTest.check(!Files.exists(game.resolve("nxeart")),
                    "nxeart excluded");
            Fable2IsoExtractorTest.check(!Files.exists(temp.resolve("files/game.pending")),
                    "staging cleaned");
            // Keep the installed game when the next attempted ISO is corrupt.
            byte[] bad = Fable2IsoExtractorTest.fixture();
            Arrays.fill(bad, 0x10000, 0x10000 + 20, (byte) 0);
            Files.write(iso, bad);
            boolean error = false;
            try {
                Fable2IsoInstaller.install(resolver, new Uri(iso.toString()), game.toFile(), null);
            } catch (IOException expected) { error = true; }
            Fable2IsoExtractorTest.check(error, "corrupted second ISO rejected");
            Fable2IsoExtractorTest.check(Files.isRegularFile(game.resolve(".import-complete")),
                    "previous install preserved on failure");
            Fable2IsoExtractorTest.check(!Files.exists(temp.resolve("files/game.pending")),
                    "failed stage removed");
            // Re-install valid ISO, verify backup was eventually cleaned.
            Files.write(iso, Fable2IsoExtractorTest.fixture());
            Fable2IsoInstaller.install(resolver, new Uri(iso.toString()), game.toFile(), null);
            Fable2IsoExtractorTest.check(!Files.exists(temp.resolve("files/game.backup")),
                    "backup cleaned after successful switch");
            Fable2IsoExtractorTest.check(Files.isRegularFile(game.resolve("default.xex")),
                    "valid installed xex available");
            System.out.println("PASS: transactional ISO installer with synthetic SAF data");
        } finally {
            try (java.util.stream.Stream<Path> paths = Files.walk(temp)) {
                paths.sorted(java.util.Comparator.reverseOrder()).forEach(p -> p.toFile().delete());
            }
        }
    }
}
