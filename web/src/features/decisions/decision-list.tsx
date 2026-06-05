import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Table, Td, Th } from "@/components/ui/table";
import {
  badgeVariantForDecisionValue,
  formatDecisionValue,
} from "./decision-list-format";
import type { DecisionListItem } from "./decision-list.types";

export function DecisionList({ decisions }: { decisions: DecisionListItem[] }) {
  return (
    <Table className="min-w-[1040px]">
      <caption className="sr-only">Projected strategy decisions</caption>
      <thead>
        <tr>
          <Th>Target</Th>
          <Th>Theme</Th>
          <Th>Earnings</Th>
          <Th>Strategy</Th>
          <Th>Evidence</Th>
          <Th>Status</Th>
          <Th>Outcome</Th>
          <Th>Mode</Th>
        </tr>
      </thead>
      <tbody>
        {decisions.map((decision) =>
          decision.malformed ? (
            <MalformedRow key={decision.decisionId} decision={decision} />
          ) : (
            <tr
              key={decision.decisionId}
              className="group transition-colors hover:bg-accent/[0.04]"
            >
              <Td className="font-medium">
                <Link
                  href={`/decisions/${encodeURIComponent(decision.decisionId)}`}
                  className="font-mono text-[0.8125rem] font-semibold tracking-tight text-foreground underline-offset-4 group-hover:text-accent group-hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                >
                  {decision.target}
                </Link>
              </Td>
              <Td className="text-muted-foreground">
                {formatDecisionValue(decision.theme)}
              </Td>
              <Td className="whitespace-nowrap text-muted-foreground">
                {formatDecisionValue(decision.earningsDate)}
              </Td>
              <Td className="text-muted-foreground">
                {formatDecisionValue(decision.strategyType)}
              </Td>
              <Td className="max-w-[24rem] text-muted-foreground">
                <span className="line-clamp-2">
                  {decision.evidenceSummary ?? "unknown"}
                </span>
              </Td>
              <Td>
                <Badge dot variant={badgeVariantForDecisionValue(decision.status)}>
                  {formatDecisionValue(decision.status)}
                </Badge>
              </Td>
              <Td>
                <Badge dot variant={badgeVariantForDecisionValue(decision.outcome)}>
                  {formatDecisionValue(decision.outcome)}
                </Badge>
              </Td>
              <Td>
                <Badge variant={badgeVariantForDecisionValue(decision.mode)}>
                  {formatDecisionValue(decision.mode)}
                </Badge>
              </Td>
            </tr>
          ),
        )}
      </tbody>
    </Table>
  );
}

function MalformedRow({ decision }: { decision: DecisionListItem }) {
  return (
    <tr className="bg-danger/5">
      <Td className="font-medium">
        <span className="flex items-center gap-1.5 font-mono text-[0.8125rem] font-semibold tracking-tight text-danger">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {decision.target}
        </span>
      </Td>
      <Td className="text-muted-foreground">{formatDecisionValue(decision.theme)}</Td>
      <Td className="whitespace-nowrap text-muted-foreground">unknown</Td>
      <Td className="text-muted-foreground">—</Td>
      <Td className="max-w-[24rem]">
        <details className="text-xs">
          <summary className="cursor-pointer font-medium text-danger focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            Show raw detail
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto rounded-card border border-danger/30 bg-background p-3 font-mono text-foreground">
            {decision.rawPayload}
          </pre>
        </details>
      </Td>
      <Td>
        <Badge dot variant="danger">
          malformed
        </Badge>
      </Td>
      <Td>
        <Badge dot variant="danger">
          malformed
        </Badge>
      </Td>
      <Td>
        <Badge variant="muted">unknown</Badge>
      </Td>
    </tr>
  );
}
