package com.nanaveone.fable2;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.view.ViewGroup;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Native-Android game-data installer. Uses the system document-tree picker;
 * no all-files-access permission, no game data included with the APK.
 *
 * Select the *extracted* Fable II game directory containing default.xex and
 * data/. This importer DOES NOT understand ISO containers.
 */
public final class Fable2LauncherActivity extends Activity {
    private static final int PICK_GAME_FOLDER = 42;
    private static final int MAX_TREE_DEPTH = 48;
    private static final int MAX_DOCUMENTS = 150000;
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private TextView status;
    private ProgressBar progress;
    private Button importButton;
    private Button playButton;
    private File gameRoot;
    private int totalDocuments;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        File external = getExternalFilesDir(null);
        gameRoot = new File(external != null ? external : getFilesDir(), "game");
        // Recover an interrupted rename from a prior import. Never silently
        // discard the previous complete installation.
        File backup = new File(gameRoot.getParentFile(), "game.backup");
        if (!gameRoot.exists() && backup.isDirectory()) {
            backup.renameTo(gameRoot);
        }
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int padding = Math.round(22 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);
        TextView heading = new TextView(this);
        heading.setText("Fable II Android");
        heading.setTextSize(25);
        layout.addView(heading);
        status = new TextView(this);
        status.setTextSize(15);
        layout.addView(status);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);
        progress.setVisibility(android.view.View.GONE);
        layout.addView(progress, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        importButton = new Button(this);
        importButton.setText("Importar pasta extraída do Fable II");
        importButton.setOnClickListener(v -> pickFolder());
        layout.addView(importButton);
        playButton = new Button(this);
        playButton.setText("Iniciar Fable II");
        playButton.setOnClickListener(v -> launchGame());
        layout.addView(playButton);
        setContentView(layout);
        updateReadyState();
    }

    private boolean hasGameFiles() {
        return new File(gameRoot, ".import-complete").isFile()
                && new File(gameRoot, "default.xex").isFile()
                && new File(gameRoot, "data").isDirectory();
    }

    private void updateReadyState() {
        boolean ready = hasGameFiles();
        playButton.setEnabled(ready);
        status.setText(ready ? "Dados locais detectados. A execução ainda depende das bibliotecas nativas compiladas."
                : "Selecione uma pasta extraída com default.xex e data/.\nNão selecione uma ISO.\n"
                + "Os dados serão copiados para o armazenamento privado do aplicativo.");
    }

    private void pickFolder() {
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(picker, PICK_GAME_FOLDER);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_GAME_FOLDER || resultCode != RESULT_OK || data == null
                || data.getData() == null) return;
        Uri tree = data.getData();
        try {
            getContentResolver().takePersistableUriPermission(tree, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (SecurityException ignored) {
            // The read grant in the activity result may still be sufficient.
        }
        importButton.setEnabled(false);
        playButton.setEnabled(false);
        progress.setVisibility(android.view.View.VISIBLE);
        totalDocuments = 0;
        status.setText("Importando os dados do jogo... Não feche o aplicativo.");
        worker.execute(() -> {
            try {
                List<GameDocument> top = listChildren(tree, DocumentsContract.getTreeDocumentId(tree));
                GameDocument xex = null;
                boolean hasData = false;
                for (GameDocument item : top) {
                    if ("default.xex".equalsIgnoreCase(item.name) && !item.directory) xex = item;
                    if ("data".equalsIgnoreCase(item.name) && item.directory) hasData = true;
                }
                if (xex == null || !hasData) {
                    throw new IOException("Pasta inválida: escolha a pasta que contém default.xex e data/");
                }
                // Check the actual executable BEFORE copying several GB of data.
                Uri xexUri = DocumentsContract.buildDocumentUriUsingTree(tree, xex.id);
                final Fable2GameCompatibility.Profile profile;
                try (InputStream source = getContentResolver().openInputStream(xexUri)) {
                    if (source == null) throw new IOException("Não foi possível ler default.xex");
                    profile = Fable2GameCompatibility.checkXex(source);
                }
                File base = gameRoot.getParentFile();
                File staging = new File(base, "game.pending");
                File backup = new File(base, "game.backup");
                // Pending is app-created and never launchable; discard only
                // that staging tree, never the user's complete game directory.
                if (staging.exists()) deleteAppOwnedTree(staging, 0);
                if (!staging.mkdirs()) throw new IOException("Não foi possível criar área temporária");
                try {
                    for (GameDocument item : top) {
                        copyDocument(tree, item, staging, staging, 0);
                    }
                    Fable2GameCompatibility.checkData(staging, profile);
                    // Re-check the local copy; an interrupted/truncated copy
                    // must never receive the completion marker.
                    try (InputStream local = new java.io.FileInputStream(new File(staging, "default.xex"))) {
                        if (!Fable2GameCompatibility.checkXex(local).id.equals(profile.id)) {
                            throw new IOException("default.xex mudou durante a importação");
                        }
                    }
                    File completed = new File(staging, ".import-complete");
                    try (FileOutputStream marker = new FileOutputStream(completed)) {
                        marker.write(("Fable II " + profile.id + " imported\n")
                                .getBytes(java.nio.charset.StandardCharsets.UTF_8));
                        marker.getFD().sync();
                    }
                    // Replace the old complete tree only after validating the
                    // entire new tree. Both paths share a parent/filesystem.
                    if (backup.exists()) {
                        if (hasGameFiles()) deleteAppOwnedTree(backup, 0);
                        else throw new IOException("Recuperação pendente em game.backup; não sobrescrever");
                    }
                    boolean movedOld = false;
                    if (gameRoot.exists()) {
                        if (!gameRoot.renameTo(backup)) {
                            throw new IOException("Não foi possível preservar instalação anterior");
                        }
                        movedOld = true;
                    }
                    if (!staging.renameTo(gameRoot)) {
                        if (movedOld && !backup.renameTo(gameRoot)) {
                            throw new IOException("Falha ao instalar e restaurar backup; preserve game.backup");
                        }
                        throw new IOException("Não foi possível finalizar importação");
                    }
                    if (movedOld) deleteAppOwnedTree(backup, 0);
                } finally {
                    // After a successful rename staging no longer exists.
                    if (staging.exists()) deleteAppOwnedTree(staging, 0);
                }
                runOnUiThread(() -> {
                    importButton.setEnabled(true);
                    progress.setVisibility(android.view.View.GONE);
                    updateReadyState();
                });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    importButton.setEnabled(true);
                    progress.setVisibility(android.view.View.GONE);
                    updateReadyState();
                    new AlertDialog.Builder(this).setTitle("Falha na importação")
                            .setMessage(error.getMessage()).setPositiveButton("OK", null).show();
                });
            }
        });
    }

    private static final class GameDocument {
        final String id;
        final String name;
        final boolean directory;
        GameDocument(String id, String name, boolean directory) {
            this.id = id;
            this.name = name;
            this.directory = directory;
        }
    }

    private List<GameDocument> listChildren(Uri tree, String parentId) throws IOException {
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parentId);
        String[] projection = {DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                DocumentsContract.Document.COLUMN_MIME_TYPE};
        ArrayList<GameDocument> results = new ArrayList<>();
        try (Cursor cursor = getContentResolver().query(children, projection, null, null, null)) {
            if (cursor == null) throw new IOException("Provedor de arquivos indisponível");
            while (cursor.moveToNext()) {
                String id = cursor.getString(0);
                String name = cursor.getString(1);
                String mime = cursor.getString(2);
                if (id == null || name == null || name.isEmpty()) continue;
                // Document providers supply names, not necessarily safe filenames.
                if (name.equals(".") || name.equals("..") || name.contains("/")
                        || name.contains("\\") || name.indexOf('\0') >= 0) {
                    throw new IOException("Nome de arquivo inválido recebido: " + name);
                }
                results.add(new GameDocument(id, name,
                        DocumentsContract.Document.MIME_TYPE_DIR.equals(mime)));
            }
        } catch (SecurityException error) {
            throw new IOException("Sem permissão para ler a pasta escolhida", error);
        }
        return results;
    }

    private void copyDocument(Uri tree, GameDocument item, File parent, File importRoot,
                              int depth) throws IOException {
        if (depth > MAX_TREE_DEPTH || ++totalDocuments > MAX_DOCUMENTS)
            throw new IOException("Limite de profundidade ou quantidade de arquivos atingido");
        String safeName = item.name;
        if (parent.equals(importRoot)) {
            if (safeName.equalsIgnoreCase("default.xex")) safeName = "default.xex";
            if (safeName.equalsIgnoreCase("data")) safeName = "data";
            if (safeName.equals(".import-complete"))
                throw new IOException("Nome reservado na pasta selecionada");
        }
        File target = new File(parent, safeName);
        String base = importRoot.getCanonicalPath() + File.separator;
        if (!target.getCanonicalPath().startsWith(base)) {
            throw new IOException("Caminho fora da pasta do aplicativo bloqueado");
        }
        if (item.directory) {
            if (!target.isDirectory() && !target.mkdirs())
                throw new IOException("Não foi possível criar " + item.name);
            for (GameDocument child : listChildren(tree, item.id)) {
                copyDocument(tree, child, target, importRoot, depth + 1);
            }
            return;
        }
        Uri document = DocumentsContract.buildDocumentUriUsingTree(tree, item.id);
        File temporary = new File(parent, safeName + ".importing");
        if (!temporary.getCanonicalPath().startsWith(base))
            throw new IOException("Destino temporário inválido");
        try (InputStream in = getContentResolver().openInputStream(document);
             FileOutputStream out = new FileOutputStream(temporary)) {
            if (in == null) throw new IOException("Não foi possível abrir " + item.name);
            byte[] buf = new byte[256 * 1024];
            int count;
            while ((count = in.read(buf)) != -1) out.write(buf, 0, count);
            out.getFD().sync();
        } catch (IOException | RuntimeException error) {
            temporary.delete();
            throw error;
        }
        if (target.exists() && !target.delete()) throw new IOException("Não foi possível substituir " + target);
        if (!temporary.renameTo(target)) throw new IOException("Não foi possível finalizar " + target);
        if (totalDocuments % 20 == 0) {
            final int count = totalDocuments;
            runOnUiThread(() -> status.setText("Arquivos processados: " + count));
        }
    }

    /** Only delete known, app-private temporary/backup trees. */
    private void deleteAppOwnedTree(File folder, int depth) throws IOException {
        if (depth > MAX_TREE_DEPTH) throw new IOException("Pasta temporária profunda demais");
        File base = gameRoot.getParentFile().getCanonicalFile();
        File canonical = folder.getCanonicalFile();
        if (!canonical.getPath().startsWith(base.getPath() + File.separator)
                || canonical.equals(gameRoot.getCanonicalFile())) {
            throw new IOException("Tentativa de apagar caminho fora da área temporária");
        }
        if (folder.isDirectory()) {
            File[] children = folder.listFiles();
            if (children == null) throw new IOException("Não foi possível listar pasta temporária");
            for (File item : children) deleteAppOwnedTree(item, depth + 1);
        }
        if (folder.exists() && !folder.delete()) {
            throw new IOException("Não foi possível remover arquivo temporário: " + folder.getName());
        }
    }

    private void launchGame() {
        if (!hasGameFiles()) {
            updateReadyState();
            return;
        }
        String libDir = getApplicationInfo().nativeLibraryDir;
        String[] required = {"libfable2.so", "librexruntime.so", "libc++_shared.so", "librexgpu-plume.so"};
        for (String name : required) {
            if (!new File(libDir, name).isFile()) {
                new AlertDialog.Builder(this).setTitle("Port nativo incompleto")
                        .setMessage("Biblioteca ausente: " + name + ". Ainda é necessário compilar o motor de Fable II.")
                        .setPositiveButton("OK", null).show();
                return;
            }
        }
        startActivity(new Intent(this, Fable2Activity.class));
    }

    @Override
    protected void onDestroy() {
        worker.shutdownNow();
        super.onDestroy();
    }
}
