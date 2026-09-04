# storage/temp/

Scratch space for short-lived files (intermediate downloads, working
files for a multi-step tool call, audio clips mid-processing). Safe to
clear on startup or periodically - nothing here is expected to survive
a restart. Keep this out of storage/backups/ and storage/exports/, which
are for durable/user-facing files.
