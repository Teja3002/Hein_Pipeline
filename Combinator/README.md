# Combinator Rules

## Combinator Rules

| Area | Rule | What it means |
|---|---|---|
| Source priority | `CrossRef -> Webscraper -> LLM` | When the same field exists in multiple matched sources, CrossRef wins first, then Webscraper, then LLM |
| Missing source file | Treat as empty | If a folder has no result in one source, the combinator still works with the others |
| Section matching | Not by section number | Sections are matched by content, not by `"1"`, `"2"`, etc. |
| First section match key | DOI exact match | If two sections have the same DOI after normalization, they are treated as the same article |
| Second section match key | Title similarity | If DOI does not match, titles are compared with normalized text and fuzzy similarity |
| Title fuzzy threshold | `>= 0.88` | Title similarity uses `SequenceMatcher`; above this threshold counts as a match |
| Third section match key | Author-set match | If DOI/title do not match, normalized author lists are compared ignoring order |
| Extra unmatched section | Keep it | If a section does not match anything, it stays as its own section in the final output |
| Same-source overwrite protection | Not allowed | One source can fill a group only once; later same-source sections create new groups instead of replacing earlier ones |
| Page matching | By `id`, then `native + section` | Pages are matched by page id first; if not, then by native page plus section chain |
| Extra unmatched page | Keep it | Unmatched page entries are also kept in the final output |
| String normalization | Lowercase, remove accents/punctuation, collapse spaces | Used for most text comparisons |
| Title normalization | Same string normalization plus fuzzy matching | Lets small punctuation/case differences still match |
| Author normalization | Normalize text, split into words, sort words | Makes `Brunk, Ingrid` equal to `Ingrid Brunk` |
| Author list normalization | Normalize each author, then sort the list | Makes author order irrelevant |
| List normalization | Normalize each item, then sort | Used for list-type field comparison |
| Empty values | Ignored for matching/conflict count | `None`, empty string, or empty list do not count as a real competing value |
| Field selection | First non-empty by priority | For matched records, the chosen field value comes from the highest-priority non-empty source |
| Conflict flag | More than 1 distinct non-empty value | If matched sources disagree on a field after normalization, that field is flagged |
| All-three-different flag | 3 sources present and all 3 distinct | Special flag when CrossRef, Webscraper, and LLM all disagree on the same field |
| Final clean output | Small result only | Final result keeps merged `pages` and trimmed `sections` fields |
| Audit output | Full provenance | Separate output file keeps per-source values, chosen source, and conflict flags |

## Section Fields In Final Result

| Included in final `sections` | Field |
|---|---|
| Yes | `title` |
| Yes | `citation` |
| Yes | `description` |
| Yes | `doi` |
| Yes | `external_url` |
| Yes | `authors` |

## Page Fields In Final Result

| Included in final `pages` | Field |
|---|---|
| Yes | `id` |
| Yes | `native` |
| Yes | `section` |
