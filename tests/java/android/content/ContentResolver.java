package android.content;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import java.io.FileInputStream;
import java.io.IOException;
/** Host-only stub of ContentResolver.openFileDescriptor. */
public final class ContentResolver {
    public ParcelFileDescriptor openFileDescriptor(Uri uri, String mode) throws IOException {
        if (!"r".equals(mode)) throw new IOException("read-only");
        return new ParcelFileDescriptor(new FileInputStream(uri.path));
    }
}
