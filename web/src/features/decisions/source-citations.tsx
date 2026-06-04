import type { SourceCitation } from "./decision-chain.types";

export function SourceCitations({
  citations,
}: {
  citations: SourceCitation[];
}) {
  if (citations.length === 0) {
    return null;
  }

  return (
    <details className="mt-4 rounded-card border border-border bg-background p-3 text-sm">
      <summary className="cursor-pointer font-medium text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
        Source citations
      </summary>
      <ul className="mt-3 space-y-3">
        {citations.map((citation) => (
          <li key={citation.citation_id} className="min-w-0">
            {citation.url ? (
              <a
                href={citation.url}
                className="break-words font-medium text-primary underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                {citation.title ?? citation.citation_id}
              </a>
            ) : (
              <span className="break-words font-medium">
                {citation.title ?? citation.citation_id}
              </span>
            )}
            <p className="mt-1 break-words text-xs text-muted-foreground">
              {citation.provider} - {citation.source_type}
              {citation.as_of ? ` - as of ${citation.as_of}` : ""}
              {citation.retrieved_at
                ? ` - retrieved ${citation.retrieved_at}`
                : ""}
            </p>
          </li>
        ))}
      </ul>
    </details>
  );
}
