# C compiler to use (override with `make CC=clang` if needed).
CC ?= gcc

# Compiler flags:
# -O2 enables optimization.
# -fPIC generates position-independent code required for shared libraries.
CFLAGS ?= -O2 -fPIC

# Linker flags:
# -shared builds a shared object (.so).
# -lm links against the C math library (libm) for pow/sqrt.
LDFLAGS ?= -shared -lm

# Output shared library name.
TARGET ?= libnative_math.so

# Input C source file to compile.
SOURCE ?= native_math.c

# These are phony targets (not real files).
.PHONY: all clean

# Default target: running `make` builds the shared library.
all: $(TARGET)

# Build rule:
# Rebuild $(TARGET) when $(SOURCE) changes or if $(TARGET) is missing.
# $@ = target file (libnative_math.so), $< = first dependency (native_math.c)
$(TARGET): $(SOURCE)
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

# Cleanup target: remove generated build artifact.
# -f prevents errors if the file does not exist.
clean:
	rm -f $(TARGET)
