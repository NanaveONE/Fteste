package android.os;
import java.io.FileDescriptor;
import java.io.FileInputStream;
import java.io.IOException;
/** Host-only stub of seekable SAF descriptor. */
public final class ParcelFileDescriptor implements java.io.Closeable {
    private final FileInputStream stream;
    private final FileDescriptor descriptor;
    public ParcelFileDescriptor(FileInputStream stream) throws IOException {
        this.stream = stream;
        descriptor = stream.getFD();
    }
    public FileDescriptor getFileDescriptor() { return descriptor; }
    public void close() throws IOException { stream.close(); }
}
