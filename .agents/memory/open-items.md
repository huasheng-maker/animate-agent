# Open Items

date: 2026-07-29
status: active

- Confirm whether the newly downloaded AgentGo protocol should be committed together with `.agents/` initialization files.
- Future frontend behavior changes should be verified in a browser, not only with static syntax checks.
- The new `NormalizedDocument` web acquisition boundary intentionally coexists with the earlier
  direct URL-to-DocumentIR API. A later approved milestone should make DocumentIR generation consume
  NormalizedDocument without importing Crawl4AI.
- A public-URL browser integration test was not made mandatory; production deployment still needs
  network-level egress restrictions to complement application SSRF checks and reduce DNS-rebinding risk.
