// Capture the current PRISM UI, not the superseded AegisOps layout.
process.argv.push("--live", "--record");
await import("./verify-prism.mjs");
