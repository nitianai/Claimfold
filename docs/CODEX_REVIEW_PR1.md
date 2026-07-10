The evidence validation can reject legitimate promotions or crash on supported evidence references. The report generator can also assign unsupported scenario semantics to arbitrary meeting state.

Full review comments:

- [P1] Normalize the statement anchor like the evidence — /home/cnhanbing/Claimfold/lib/claim_lifecycle.py:207-207
  `_normalize_for_anchor()` removes all whitespace, while this function preserves collapsed spaces. For any statement such as `Revenue grew 10%`, the anchor contains spaces but the normalized evidence does not, so promotion is rejected even when the evidence contains the exact statement. Normalize both sides identically before matching.

- [P2] Reject or expand directory evidence before reading — /home/cnhanbing/Claimfold/lib/claim_lifecycle.py:194-194
  When an allowed evidence reference is a directory such as `raw/`—the same representation emitted by the response parser when no specific raw path is supplied—`exists()` succeeds and `read_text()` raises `IsADirectoryError`. This aborts `claim promote` instead of returning a validation result; validate that the path is a file or explicitly search directory contents.

- [P2] Require structured data before labeling scenarios — /home/cnhanbing/Claimfold/lib/runtime_ext.py:602-605
  For reports below the mock threshold with any confirmed point, this assigns the first state items positionally to Scenario A/B/C and fills remaining slots from `conflicts`. Those fields are not scenario-typed, so ordinary facts or unrelated disagreements are presented as baseline, escalation, or reversal scenarios that the meeting never produced. Only explicitly structured scenario entries should receive these labels; otherwise report that scenarios are absent.