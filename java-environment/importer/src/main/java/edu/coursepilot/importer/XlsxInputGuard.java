package edu.coursepilot.importer;

import static edu.coursepilot.importer.ImportModels.IssueCode.EXTERNAL_LINK_PRESENT;
import static edu.coursepilot.importer.ImportModels.IssueCode.FILE_TOO_LARGE;
import static edu.coursepilot.importer.ImportModels.IssueCode.INVALID_OOXML;
import static edu.coursepilot.importer.ImportModels.IssueCode.WRONG_EXTENSION;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public final class XlsxInputGuard {
  public static final int MAX_BYTES = 10 * 1024 * 1024;
  private static final long MAX_UNCOMPRESSED_BYTES = 64L * 1024 * 1024;

  byte[] read(Path path) throws ImportRejectedException {
    if (path == null || path.getFileName() == null) {
      throw new ImportRejectedException(INVALID_OOXML);
    }
    if (!path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".xlsx")) {
      throw new ImportRejectedException(WRONG_EXTENSION);
    }
    try {
      long size = Files.size(path);
      if (size <= 0 || size > MAX_BYTES) {
        throw new ImportRejectedException(FILE_TOO_LARGE);
      }
      byte[] bytes = Files.readAllBytes(path);
      if (bytes.length < 4
          || bytes[0] != 'P'
          || bytes[1] != 'K'
          || (bytes[2] != 3 && bytes[2] != 5 && bytes[2] != 7)) {
        throw new ImportRejectedException(INVALID_OOXML);
      }
      try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(bytes))) {
        ZipEntry entry;
        long uncompressedBytes = 0;
        int entryCount = 0;
        byte[] buffer = new byte[8192];
        while ((entry = zip.getNextEntry()) != null) {
          entryCount++;
          if (entryCount > 256) {
            throw new ImportRejectedException(INVALID_OOXML);
          }
          if (entry.getName().equalsIgnoreCase("xl/vbaProject.bin")) {
            throw new ImportRejectedException(INVALID_OOXML);
          }
          if (entry.getName().toLowerCase(Locale.ROOT).startsWith("xl/externallinks/")) {
            throw new ImportRejectedException(EXTERNAL_LINK_PRESENT);
          }
          int read;
          while ((read = zip.read(buffer)) != -1) {
            uncompressedBytes += read;
            if (uncompressedBytes > MAX_UNCOMPRESSED_BYTES) {
              throw new ImportRejectedException(FILE_TOO_LARGE);
            }
          }
        }
      }
      return bytes;
    } catch (IOException e) {
      throw new ImportRejectedException(INVALID_OOXML);
    }
  }

  public static final class ImportRejectedException extends RuntimeException {
    private final ImportModels.IssueCode code;

    ImportRejectedException(ImportModels.IssueCode code) {
      super(code.name());
      this.code = code;
    }

    public ImportModels.IssueCode code() {
      return code;
    }
  }
}
