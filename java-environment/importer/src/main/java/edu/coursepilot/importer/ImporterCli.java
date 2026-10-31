package edu.coursepilot.importer;

import java.nio.file.Path;

/** Local diagnostic entry point; it prepares a draft but never publishes it. */
public final class ImporterCli {
  private ImporterCli() {}

  public static void main(String[] args) {
    if (args.length != 2) {
      System.err.println("Usage: ImporterCli <xlsx-path> <track-id>");
      System.exit(2);
    }
    try {
      var draft = new A1WorkbookImporter().prepare(Path.of(args[0]), args[1]);
      System.out.printf(
          "track=%s publishable=%s requirements=%d entries=%d issues=%d blocking=%d recorded=%d"
              + " key=%s%n",
          draft.trackId(),
          draft.publishable(),
          draft.requirements().size(),
          draft.entries().size(),
          draft.issues().size(),
          draft.blockingIssues().size(),
          draft.recordedIssues().size(),
          draft.idempotencyKey());
      draft
          .issues()
          .forEach(
              issue ->
                  System.out.printf(
                      "issue=%s sheet=%s row=%d column=%d%n",
                      (issue.code().blocking() ? "BLOCK " : "RECORD ") + issue.code(),
                      issue.sheet(),
                      issue.row(),
                      issue.column()));
      if (!draft.publishable()) System.exit(1);
    } catch (XlsxInputGuard.ImportRejectedException e) {
      System.err.println("rejected=" + e.code());
      System.exit(1);
    }
  }
}
