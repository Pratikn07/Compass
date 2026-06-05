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
            <dl className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
              {citation.confidence ? (
                <CitationDetail
                  label="Evidence confidence"
                  value={citation.confidence}
                />
              ) : null}
              {citation.source_endpoint ? (
                <CitationDetail
                  label="Endpoint"
                  value={citation.source_endpoint}
                />
              ) : null}
              {citation.source_id ? (
                <CitationDetail label="Source id" value={citation.source_id} />
              ) : null}
              {citation.as_of ? (
                <CitationDetail label="As of" value={citation.as_of} />
              ) : null}
              {citation.retrieved_at ? (
                <CitationDetail
                  label="Retrieved"
                  value={citation.retrieved_at}
                />
              ) : null}
            </dl>
            {citation.excerpt ? (
              <p className="mt-2 break-words border-l-2 border-border pl-3 text-xs text-foreground">
                {citation.excerpt}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

function CitationDetail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 break-words">
      <dt className="sr-only">{label}</dt>
      <dd>
        {label}: {value}
      </dd>
    </div>
  );
}
