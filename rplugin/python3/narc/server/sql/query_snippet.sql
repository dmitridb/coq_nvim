SELECT
  snippets.suggestions_id AS suggestions_id,
  snippet_kinds.kind AS kind,
  snippets.content AS content
FROM snippets
JOIN snippet_kinds
ON
  snippet_kinds.rowid = snippets.snippet_kind_id;
WHERE
  snippets.suggestions_id = ?
