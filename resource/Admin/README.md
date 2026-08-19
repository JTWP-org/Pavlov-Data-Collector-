# JTWP Expanded Moderation Rules

This revision makes the admin-selected category separate from the written rule.

A moderation case does **not** become invalid merely because no existing rule
perfectly describes the behavior.

## Admin review flow

1. Admin selects the category that best describes the incident.
2. Admin selects an existing rule if one fits.
3. If none fits, select `OTHER` / `No Existing Rule`.
4. The case remains valid.
5. The case is automatically flagged `NEEDS_RULE_REVIEW`.
6. Senior administration can still approve a warning/ban.
7. Administration later decides whether a new rule or category should be added.

This preserves moderator judgment without silently inventing a rule after the
incident.

## Files

- `moderation_categories.json` — canonical category list.
- `moderation_policy.json` — decision policy, including unmatched-case behavior.
- `rules_and_punishments.json` — expanded rule definitions and guidance.
- `rules_list.json` — compact display list for Discord.
- `moderation_case_schema.json` — fields the case system should store.

## Important distinction

`matched_rule_id` may be `null`.

`case_valid` may still be `true`.

The bot should never automatically reject a case solely because
`matched_rule_id` is missing.
