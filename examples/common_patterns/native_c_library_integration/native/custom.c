// Minimal native C library used by this example connector.
// It is compiled into a shared object (libcustom.so) by drivers/installation.sh
// at deploy time, then loaded from connector code via ctypes (see native_wrapper.py).
//
// Replace this with your own vendored C source, or drop a pre-built .so file
// into this folder instead and remove the compilation step from installation.sh.

// Simple integer addition exposed to Python via ctypes.
int add(int a, int b) {
    return a + b;
}
