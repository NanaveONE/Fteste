package com.nanaveone.fable2;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/**
 * The XEX hashes/lengths come from the pinned Fable-2-Recomp
 * constants/game_versions.json. No executable or game content is bundled.
 * Re-check the table against the pinned submodule when it is upgraded.
 */
final class Fable2GameCompatibility {
    private static final long XEX_BYTES = 21217280L;

    static final class Profile {
        final String id;
        final String sha256;
        final boolean requiresGermanBook;

        Profile(String id, String sha256, boolean requiresGermanBook) {
            this.id = id;
            this.sha256 = sha256;
            this.requiresGermanBook = requiresGermanBook;
        }
    }

    private static final Profile[] SUPPORTED = {
        new Profile("goty-us-eu", "88c4ef2e18e65409444d1b068eff921d1f7e180a5ae64edc64ba6b0872372662", false),
        new Profile("goty-german", "3f36e7870a06e04b3702760e93c61b1c7fded321b94021da6bfa120b424e6eb4", true),
        new Profile("goty-french", "0e1ea96ded3407874cbbb3a9587d79f1340a57a9d1ba2feebcfdbc9ed1e4b6e5", false),
        new Profile("goty-italy", "27a7ad9d66df4131a7fc352829d9df4df40206350ec63c7ee1b53bd71b203da0", false),
        new Profile("goty-russia", "aaf100ce83994d178c6585ab502babfd6b3c9d0739017e96e6e5d61bcbbca943", false),
        new Profile("goty-spain", "6422e22327b576f6d188206ab00112eedc780f3d130a45ca6ac42f7e4b99da6c", false),
    };

    private Fable2GameCompatibility() {}

    /** Inspect only the supplied XEX; no game bytes are uploaded or retained. */
    static Profile checkXex(InputStream in) throws IOException {
        final MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException failure) {
            throw new IOException("SHA-256 indisponível", failure);
        }
        byte[] buffer = new byte[128 * 1024];
        long count = 0;
        int n;
        while ((n = in.read(buffer)) != -1) {
            count += n;
            if (count > XEX_BYTES) throw new IOException("default.xex maior que as edições compatíveis");
            digest.update(buffer, 0, n);
        }
        if (count != XEX_BYTES) {
            throw new IOException("default.xex de tamanho incompatível (" + count + " bytes)");
        }
        StringBuilder hex = new StringBuilder(64);
        for (byte byteValue : digest.digest()) {
            int value = byteValue & 0xff;
            hex.append(Character.forDigit(value >>> 4, 16));
            hex.append(Character.forDigit(value & 15, 16));
        }
        String hash = hex.toString();
        for (Profile item : SUPPORTED) {
            if (item.sha256.equals(hash)) return item;
        }
        throw new IOException("Edição não suportada pelo Fable-2-Recomp. Verifique sua cópia original GOTY (SHA-256 diferente).");
    }

    static void checkData(File root, Profile profile) throws IOException {
        if (!new File(root, "default.xex").isFile() || !new File(root, "data").isDirectory()) {
            throw new IOException("Faltam default.xex ou data/");
        }
        for (String file : new String[]{"data/gold_version.txt", "data/startup.vfsconfig"}) {
            if (!new File(root, file).isFile()) {
                throw new IOException("Arquivo obrigatório ausente: " + file);
            }
        }
        if (new File(root, "data/tu1_data.bnk").exists()) {
            throw new IOException("Conteúdo TU1 misturado com versão GOTY compatível");
        }
        if (profile.requiresGermanBook &&
                !new File(root, "data/language/de-de/text/book.babel").isFile()) {
            throw new IOException("Edição alemã: falta data/language/de-de/text/book.babel");
        }
    }
}
