# Utility skills

New in Phase 4 - stdlib-only, no optional dependencies to install.

| Action (via `get_skill("utilities").execute(...)`) | What it does |
|---|---|
| text_stats, slugify, truncate, change_case, similarity | Text helpers |
| convert_length, convert_weight, convert_temperature | Unit conversion |
| current_time, add_time, time_between | Date/time math |
| hash_text, encode_base64, decode_base64 | Hashing / encoding |
| generate_password, generate_uuid, roll_dice, flip_coin, random_number | Random generation |

Implemented in `skills/utilities/tools.py` (`UtilityTools`, extends `BaseSkill`).
Not yet wired into `ai/tools_schema.py` / `core/executor.py` for direct AI
tool-calling - call it via the skill registry (`skills.get_skill("utilities")`)
or add entries to those files following the pattern documented in
`skills/windows/MANIFEST.md` if you want the AI to call these directly.
