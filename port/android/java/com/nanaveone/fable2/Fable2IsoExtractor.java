package com.nanaveone.fable2;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Read a retail Xbox 360 GDFX ISO for the SAME Fable II supported by
 * himdo/Fable-2-Recomp. Port of the wire format in tools/x360extract/lib/Gdfx.cs.
 * No .NET runtime, original game bytes or network access is included.
 *
 * The caller provides a seekable Android SAF FileChannel, and decides which
 * root entries are extracted. This class never writes files outside its root.
 */
final class Fable2IsoExtractor {
    static final byte[] MAGIC = "MICROSOFT*XBOX*MEDIA".getBytes(StandardCharsets.US_ASCII);
    private static final int SECTOR = 2048;
    private static final int COPY_BUFFER = 256 * 1024;
    private static final int SCAN_BUFFER = 4 * 1024 * 1024;
    private static final int MAX_DEPTH = 48;
    private static final int MAX_ENTRIES = 150000;
    private static final long MAX_DIR_SIZE = 64L * 1024 * 1024;
    private final FileChannel source;
    private final long length;
    private final long baseOffset;
    private final List<Entry> root;
    private int entriesSeen;
    private final Set<String> expandedDirs = new HashSet<>();

    interface Progress {
        void onProgress(String name, long bytesWritten, long bytesTotal);
    }

    static final class Entry {
        final String name;
        final long sector;
        final long size;
        final boolean directory;
        Entry(String name, long sector, long size, boolean directory) {
            this.name = name;
            this.sector = sector;
            this.size = size;
            this.directory = directory;
        }
    }

    Fable2IsoExtractor(FileChannel source) throws IOException {
        this.source = source;
        this.length = source.size();
        if (length < 0x10000 + 36) throw new IOException("ISO curta demais para GDFX");
        long header = scanHeader();
        if (header < 0x10000 || header + 36 > length) {
            throw new IOException("Cabeçalho GDFX fora do disco");
        }
        baseOffset = header - 0x10000;
        byte[] hdr = readExact(header, 36);
        for (int i = 0; i < MAGIC.length; i++) {
            if (hdr[i] != MAGIC[i]) throw new IOException("Assinatura GDFX inválida");
        }
        long rootSector = u32(hdr, 20);
        long rootSize = u32(hdr, 24);
        root = readDirectory(rootSector, rootSize, 0);
    }

    List<Entry> getRoot() {
        return new ArrayList<>(root);
    }

    Entry rootFile(String wanted) throws IOException {
        for (Entry item : root) {
            if (!item.directory && item.name.equalsIgnoreCase(wanted)) return item;
        }
        throw new IOException("ISO do Fable II não contém " + wanted);
    }

    Entry rootDirectory(String wanted) throws IOException {
        for (Entry item : root) {
            if (item.directory && item.name.equalsIgnoreCase(wanted)) return item;
        }
        throw new IOException("ISO do Fable II não contém a pasta " + wanted + "/");
    }

    /** Extract only the requested Fable II content, never firmware or STFS. */
    void extractDataDirectory(Entry data, File staging, Progress progress) throws IOException {
        if (!data.directory || !data.name.equalsIgnoreCase("data")) {
            throw new IOException("Entrada data/ inválida");
        }
        File target = new File(staging, "data");
        if (!target.isDirectory() && !target.mkdirs()) {
            throw new IOException("Não foi possível criar data/");
        }
        expandedDirs.clear();
        extractChildren(data, target, 1, progress);
    }

    /** Read directly from ISO; fail if the declared payload is truncated. */
    void extractFile(Entry file, File destination, Progress progress) throws IOException {
        if (file.directory) throw new IOException("Tentativa de extrair pasta como arquivo");
        long offset = fileOffset(file.sector, file.size);
        File parent = destination.getParentFile();
        if (parent == null || (!parent.isDirectory() && !parent.mkdirs())) {
            throw new IOException("Não foi possível criar destino de extração");
        }
        byte[] buffer = new byte[COPY_BUFFER];
        long done = 0;
        try (FileOutputStream output = new FileOutputStream(destination)) {
            while (done < file.size) {
                if (Thread.currentThread().isInterrupted()) throw new IOException("Extração interrompida");
                int chunk = (int) Math.min(buffer.length, file.size - done);
                readFully(offset + done, buffer, chunk);
                output.write(buffer, 0, chunk);
                done += chunk;
                if (progress != null) progress.onProgress(file.name, done, file.size);
            }
            output.getFD().sync();
        } catch (IOException | RuntimeException error) {
            destination.delete();
            throw error;
        }
        if (destination.length() != file.size) {
            destination.delete();
            throw new IOException("Arquivo da ISO truncado: " + file.name);
        }
    }

    private void extractChildren(Entry parent, File target, int depth, Progress progress)
            throws IOException {
        if (depth > MAX_DEPTH) throw new IOException("Pastas GDFX profundas demais");
        String identity = parent.sector + ":" + parent.size;
        if (!expandedDirs.add(identity)) throw new IOException("Ciclo ou pasta GDFX repetida");
        for (Entry item : readDirectory(parent.sector, parent.size, depth)) {
            String name = item.name;
            if (name.equals(".import-complete") || name.endsWith(".importing")) {
                throw new IOException("Nome de arquivo reservado na ISO");
            }
            File path = new File(target, name);
            if (item.directory) {
                if (!path.isDirectory() && !path.mkdirs()) {
                    throw new IOException("Não foi possível criar " + name);
                }
                extractChildren(item, path, depth + 1, progress);
            } else {
                extractFile(item, path, progress);
            }
        }
    }

    private List<Entry> readDirectory(long sector, long size, int depth) throws IOException {
        if (depth > MAX_DEPTH || size < 0 || size > MAX_DIR_SIZE || (size % SECTOR) != 0) {
            throw new IOException("Tamanho de diretório GDFX inválido");
        }
        long start = fileOffset(sector, size);
        long end = start + size;
        long pos = start;
        List<Entry> result = new ArrayList<>();
        Set<String> names = new HashSet<>();
        while (pos + 14 <= end) {
            byte[] rec = readExact(pos, 14);
            if (u32(rec, 0) == 0xffffffffL) {
                long next = start + ((((pos - start) / SECTOR) + 1) * SECTOR);
                if (next < end && allFF(pos, (int) (next - pos))) {
                    pos = next;
                    continue;
                }
                break;
            }
            int nameLen = rec[13] & 255;
            if (nameLen < 1 || nameLen > 100 || pos + 14 + nameLen > end) {
                throw new IOException("Entrada de diretório GDFX inválida");
            }
            byte[] rawName = readExact(pos + 14, nameLen);
            String name = new String(rawName, StandardCharsets.US_ASCII);
            checkName(rawName, name);
            String key = name.toLowerCase(java.util.Locale.ROOT);
            if (!names.add(key)) throw new IOException("Nome repetido no disco: " + name);
            long fileSector = u32(rec, 4);
            long fileSize = u32(rec, 8);
            boolean directory = (rec[12] & 0x10) != 0;
            if (directory) {
                if (fileSize > MAX_DIR_SIZE || fileSize % SECTOR != 0)
                    throw new IOException("Subdiretório GDFX inválido: " + name);
                fileOffset(fileSector, fileSize);
            } else {
                fileOffset(fileSector, fileSize);
            }
            if (++entriesSeen > MAX_ENTRIES) throw new IOException("Muitas entradas GDFX");
            result.add(new Entry(name, fileSector, fileSize, directory));
            pos += (14 + nameLen + 3) & ~3;
        }
        return result;
    }

    private static void checkName(byte[] raw, String name) throws IOException {
        if (name.equals(".") || name.equals("..")) throw new IOException("Caminho GDFX inseguro");
        for (byte b : raw) {
            int c = b & 255;
            if (c <= 0x20 || c >= 0x7f || c == '/' || c == '\\' || c == ':') {
                throw new IOException("Nome GDFX inseguro: " + name);
            }
        }
    }

    private long fileOffset(long sector, long size) throws IOException {
        long offset = baseOffset + sector * SECTOR;
        if (offset < 0 || size < 0 || offset > length || size > length - offset) {
            throw new IOException("Setor GDFX aponta para fora da ISO");
        }
        return offset;
    }

    private long scanHeader() throws IOException {
        byte[] buf = new byte[SCAN_BUFFER + MAGIC.length];
        long offset = 0;
        int overlap = 0;
        while (offset < length) {
            if (Thread.currentThread().isInterrupted()) throw new IOException("Varredura interrompida");
            int count = (int) Math.min(SCAN_BUFFER, length - offset);
            readFully(offset, buf, count, overlap);
            int limit = overlap + count - MAGIC.length;
            for (int i = 0; i <= limit; i++) {
                if (buf[i] == MAGIC[0]) {
                    boolean match = true;
                    for (int j = 1; j < MAGIC.length; j++) {
                        if (buf[i + j] != MAGIC[j]) { match = false; break; }
                    }
                    if (match) return offset - overlap + i;
                }
            }
            int windowBytes = overlap + count;
            int keep = Math.min(MAGIC.length - 1, windowBytes);
            System.arraycopy(buf, windowBytes - keep, buf, 0, keep);
            overlap = keep;
            offset += count;
        }
        throw new IOException("Cabeçalho GDFX não encontrado. Selecione uma ISO Xbox 360 completa.");
    }

    private boolean allFF(long offset, int count) throws IOException {
        byte[] bytes = readExact(offset, count);
        for (byte value : bytes) if ((value & 255) != 255) return false;
        return true;
    }

    private byte[] readExact(long offset, int count) throws IOException {
        byte[] result = new byte[count];
        readFully(offset, result, count);
        return result;
    }

    private void readFully(long offset, byte[] bytes, int count) throws IOException {
        readFully(offset, bytes, count, 0);
    }

    private void readFully(long offset, byte[] bytes, int count, int destOffset) throws IOException {
        ByteBuffer dst = ByteBuffer.wrap(bytes, destOffset, count);
        while (dst.hasRemaining()) {
            int n = source.read(dst, offset);
            if (n <= 0) throw new IOException("Não foi possível ler ISO aleatoriamente; escolha um arquivo local.");
            offset += n;
        }
    }

    private static long u32(byte[] bytes, int index) {
        return ((long) bytes[index] & 255) |
                (((long) bytes[index + 1] & 255) << 8) |
                (((long) bytes[index + 2] & 255) << 16) |
                (((long) bytes[index + 3] & 255) << 24);
    }
}
