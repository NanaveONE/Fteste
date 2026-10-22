package com.nanaveone.fable2;

import android.content.ContentResolver;
import android.net.Uri;
import android.os.ParcelFileDescriptor;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.file.Files;

/**
 * Transactional ISO installer for the *same* GOTY Fable II version supported
 * by himdo/Fable-2-Recomp. All extraction stays in application-specific storage.
 */
final class Fable2IsoInstaller {
    interface Progress {
        void onProgress(String text);
    }

    private Fable2IsoInstaller() {}

    static void install(ContentResolver resolver, Uri isoUri, File gameRoot, Progress progress)
            throws IOException {
        File base = gameRoot.getParentFile();
        if (base == null || (!base.isDirectory() && !base.mkdirs()))
            throw new IOException("Armazenamento do aplicativo indisponível");
        File pending = new File(base, "game.pending");
        File backup = new File(base, "game.backup");
        if (pending.exists()) deleteOwned(pending, base, 0);
        if (!pending.mkdirs()) throw new IOException("Não foi possível criar área temporária");
        boolean committed = false;
        try {
            if (progress != null) progress.onProgress("Analisando ISO Xbox 360...");
            try (ParcelFileDescriptor descriptor = resolver.openFileDescriptor(isoUri, "r")) {
                if (descriptor == null) throw new IOException("Não foi possível abrir a ISO");
                // FileInputStream is merely a channel to the seekable SAF fd;
                // no multi-gigabyte duplicate ISO is copied to app storage.
                try (FileInputStream input = new FileInputStream(descriptor.getFileDescriptor());
                     FileChannel channel = input.getChannel()) {
                    Fable2IsoExtractor disc = new Fable2IsoExtractor(channel);
                    Fable2IsoExtractor.Entry xex = disc.rootFile("default.xex");
                    Fable2IsoExtractor.Entry data = disc.rootDirectory("data");
                    if (progress != null) progress.onProgress("Verificando versão GOTY do Fable II...");
                    File extractedXex = new File(pending, "default.xex");
                    disc.extractFile(xex, extractedXex, null);
                    Fable2GameCompatibility.Profile profile;
                    try (FileInputStream check = new FileInputStream(extractedXex)) {
                        profile = Fable2GameCompatibility.checkXex(check);
                    }
                    if (progress != null) progress.onProgress("Extraindo data/ do Fable II...");
                    final long[] lastUi = {0};
                    disc.extractDataDirectory(data, pending, (name, done, total) -> {
                        if (progress != null && (done - lastUi[0] > 16L * 1024 * 1024 || done == total)) {
                            lastUi[0] = done;
                            progress.onProgress("Extraindo " + name + " (" + done / (1024 * 1024) + " MiB)");
                        }
                    });
                    Fable2GameCompatibility.checkData(pending, profile);
                    try (FileInputStream check = new FileInputStream(extractedXex)) {
                        if (!Fable2GameCompatibility.checkXex(check).id.equals(profile.id))
                            throw new IOException("default.xex mudou durante a extração");
                    }
                    // Never declare the installation ready until data and XEX
                    // have both passed the ORIGINAL game's compatibility gate.
                    try (FileOutputStream marker = new FileOutputStream(new File(pending, ".import-complete"))) {
                        marker.write(("Fable II " + profile.id + " ISO imported\n")
                                .getBytes(StandardCharsets.UTF_8));
                        marker.getFD().sync();
                    }
                }
            } catch (IllegalArgumentException error) {
                throw new IOException("Provedor da ISO não permite acesso aleatório ao arquivo", error);
            }
            // Use exactly the same game/, game.pending/, game.backup layout as
            // the pre-existing folder importer. Preserve the previous install
            // until the complete replacement is validated.
            if (backup.exists()) {
                if (isComplete(gameRoot)) deleteOwned(backup, base, 0);
                else throw new IOException("Recuperação pendente em game.backup; não sobrescrever");
            }
            boolean movedOld = false;
            if (gameRoot.exists()) {
                if (!gameRoot.renameTo(backup)) throw new IOException("Falha ao preservar instalação antiga");
                movedOld = true;
            }
            if (!pending.renameTo(gameRoot)) {
                if (movedOld && !backup.renameTo(gameRoot))
                    throw new IOException("Falha ao restaurar backup; preserve game.backup");
                throw new IOException("Falha ao finalizar instalação da ISO");
            }
            committed = true;
            if (movedOld) deleteOwned(backup, base, 0);
            if (progress != null) progress.onProgress("Dados de Fable II instalados; motor Android ainda é necessário.");
        } finally {
            if (!committed && pending.exists()) deleteOwned(pending, base, 0);
        }
    }

    private static boolean isComplete(File root) {
        return new File(root, ".import-complete").isFile()
                && new File(root, "default.xex").isFile() && new File(root, "data").isDirectory();
    }

    private static void deleteOwned(File path, File base, int depth) throws IOException {
        if (depth > 48) throw new IOException("Árvore temporária profunda demais");
        File baseCanonical = base.getCanonicalFile();
        File candidate = path.getCanonicalFile();
        if (!candidate.getPath().startsWith(baseCanonical.getPath() + File.separator)
                || candidate.equals(new File(baseCanonical, "game"))
                || Files.isSymbolicLink(path.toPath())) {
            throw new IOException("Exclusão de caminho inseguro bloqueada");
        }
        if (path.isDirectory()) {
            File[] children = path.listFiles();
            if (children == null) throw new IOException("Falha ao listar temporário");
            for (File child : children) deleteOwned(child, base, depth + 1);
        }
        if (path.exists() && !path.delete()) throw new IOException("Falha ao limpar " + path.getName());
    }
}
