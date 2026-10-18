// Capture the current PRISM UI, not the superseded Kairos AI layout.
process.argv.push("--live", "--record");
await import("./verify-prism.mjs");
