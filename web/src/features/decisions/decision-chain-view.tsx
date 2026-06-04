import Link from "next/link";
import { CheckCircle2, Info, Lock, XCircle } from "lucide-react";
import { ErrorState } from "@/components/states/error-state";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import {
  badgeVariantForChainStatus,
  formatChainValue,
  formatList,
  formatMoney,
} from "./decision-chain-format";
import type {
  AnalystReviewPayload,
  DecisionChainRecord,
  ExecutionProposalPayload,
  PositionSizingPayload,
  RiskDecisionPayload,
  SourceCitation,
  StrategyDecisionPayload,
  TradeOutcomePayload,
} from "./decision-chain.types";
import { SourceCitations } from "./source-citations";

export function DecisionChainView({
  decisionId,
  records,
}: {
  decisionId: string;
  records: DecisionChainRecord[];
}) {
  const metadata = firstRecordMetadata(records);

  return (
    <section className="min-w-0 space-y-6">
      <div className="flex min-w-0 flex-col gap-4 border-b border-border pb-5 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0 space-y-2">
          <Link
            href="/decisions"
            className="text-sm font-medium text-muted-foreground underline-offset-2 hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-primary"
          >
            Back to decisions
          </Link>
          <div className="min-w-0">
            <h1 className="break-words text-2xl font-semibold tracking-tight">
              <span className="font-mono">{metadata.target}</span> decision chain
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Theme: {metadata.theme}
            </p>
          </div>
        </div>
        <dl className="grid min-w-0 gap-2 text-sm md:min-w-72">
          <div className="min-w-0">
            <dt className="sr-only">Decision id</dt>
            <dd className="break-all font-medium">Decision: {decisionId}</dd>
          </div>
          <div className="min-w-0">
            <dt className="sr-only">Run id</dt>
            <dd className="break-all font-medium">Run: {metadata.runId}</dd>
          </div>
        </dl>
      </div>

      <ol
        aria-label="Decision chain audit trail"
        className="grid min-w-0 gap-5"
      >
        {records.map((record, index) => (
          <DecisionChainRecordCard
            key={record.row.journal_record_id}
            isLast={index === records.length - 1}
            record={record}
            stepNumber={index + 1}
          />
        ))}
      </ol>
    </section>
  );
}

function DecisionChainRecordCard({
  isLast,
  record,
  stepNumber,
}: {
  isLast: boolean;
  record: DecisionChainRecord;
  stepNumber: number;
}) {
  const headingId = `${record.row.journal_record_id}-heading`;
  const isRisk = record.recordType === "risk_decision";
  const status = getRecordStatus(record);

  return (
    <li className="grid min-w-0 grid-cols-[1.75rem_minmax(0,1fr)] gap-x-4">
      <div className="relative flex justify-center">
        <span
          aria-hidden="true"
          className={cn(
            "mt-5 flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold tabular-nums",
            isRisk
              ? "border-primary bg-primary text-primary-foreground shadow-sm"
              : "border-border-strong bg-card text-muted-foreground",
          )}
        >
          {stepNumber}
        </span>
        {isLast ? null : (
          <span
            aria-hidden="true"
            className="absolute top-12 bottom-[-1.25rem] w-px bg-border"
          />
        )}
      </div>
      <article
        aria-labelledby={headingId}
        className={cn(
          "min-w-0 rounded-card border border-border bg-card p-5 shadow-sm shadow-primary/[0.03] transition-shadow",
          isRisk &&
            "border-primary shadow-md ring-1 ring-primary/15 border-l-4 border-l-primary",
        )}
        data-testid={`${record.recordType.replaceAll("_", "-")}-card`}
      >
        <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
              {isRisk ? "Risk gate · Step" : "Step"} {stepNumber}
            </p>
            <h2
              id={headingId}
              className="mt-1 break-words text-lg font-semibold tracking-tight"
            >
              {record.label}
            </h2>
            <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
              {record.row.created_at}
            </p>
          </div>
          <Badge dot variant={badgeVariantForChainStatus(status)}>
            {formatChainValue(status)}
          </Badge>
        </div>

        <div className="mt-4 min-w-0">
          {record.payload.ok ? (
            <ParsedPayloadContent record={record} />
          ) : (
            <ErrorState
              detail={formatJson(record.payload.raw)}
              title={`Malformed ${record.recordType} payload`}
            />
          )}
        </div>
      </article>
    </li>
  );
}

function ParsedPayloadContent({ record }: { record: DecisionChainRecord }) {
  if (!record.payload.ok) {
    return null;
  }

  switch (record.recordType) {
    case "strategy_decision":
      return (
        <StrategyContent
          payload={record.payload.data as StrategyDecisionPayload}
          citations={record.payload.citations}
        />
      );
    case "analyst_review":
      return (
        <AnalystContent
          payload={record.payload.data as AnalystReviewPayload}
          citations={record.payload.citations}
        />
      );
    case "risk_decision":
      return (
        <RiskContent
          payload={record.payload.data as RiskDecisionPayload}
          citations={record.payload.citations}
        />
      );
    case "position_sizing":
      return (
        <PositionSizingContent
          payload={record.payload.data as PositionSizingPayload}
          citations={record.payload.citations}
        />
      );
    case "execution_proposal":
      return (
        <ExecutionProposalContent
          payload={record.payload.data as ExecutionProposalPayload}
        />
      );
    case "trade_outcome":
    case "outcome_correction":
      return (
        <OutcomeContent payload={record.payload.data as TradeOutcomePayload} />
      );
  }
}

function StrategyContent({
  citations,
  payload,
}: {
  citations: SourceCitation[];
  payload: StrategyDecisionPayload;
}) {
  const candidate = payload.candidate_brief;

  return (
    <div className="min-w-0 space-y-4 text-sm">
      <p className="break-words border-l-2 border-border-strong pl-3 text-[0.9375rem] leading-relaxed text-foreground">
        {payload.thesis}
      </p>
      <dl className="grid gap-3 sm:grid-cols-2">
        <MetadataItem label="Status" value={payload.strategy_decision.status} />
        <MetadataItem
          label="Expression"
          value={candidate?.recommended_expression ?? "unknown"}
        />
        <MetadataItem
          label="Peer signal score"
          value={String(candidate?.peer_signal_score ?? "unknown")}
        />
        <MetadataItem
          label="Rejection reasons"
          value={formatList(payload.rejection_reasons)}
        />
      </dl>
      <SourceCitations citations={citations} />
    </div>
  );
}

function AnalystContent({
  citations,
  payload,
}: {
  citations: SourceCitation[];
  payload: AnalystReviewPayload;
}) {
  return (
    <div className="min-w-0 space-y-4 text-sm">
      <p className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 font-medium text-primary">
        <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
        Advisory only, not authorization.
      </p>
      <dl className="grid gap-3 sm:grid-cols-2">
        <MetadataItem
          label="Recommendation"
          value={payload.analysis?.recommendation ?? "unknown"}
        />
        <MetadataItem
          label="Conviction"
          value={
            payload.analysis?.conviction_score == null
              ? "unknown"
              : String(payload.analysis.conviction_score)
          }
        />
      </dl>
      {payload.analysis?.reasoning ? (
        <p className="break-words text-muted-foreground">
          {payload.analysis.reasoning}
        </p>
      ) : null}
      <SourceCitations citations={citations} />
    </div>
  );
}

function RiskContent({
  citations,
  payload,
}: {
  citations: SourceCitation[];
  payload: RiskDecisionPayload;
}) {
  const risk = payload.risk_gate_decision;
  const allowed = risk.broker_execution_allowed;

  return (
    <div className="min-w-0 space-y-4 text-sm">
      <p className="break-words text-base font-medium text-foreground">
        {risk.explanation}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2">
          {allowed ? (
            <CheckCircle2
              className="h-4 w-4 shrink-0 text-success"
              aria-hidden="true"
            />
          ) : (
            <XCircle
              className="h-4 w-4 shrink-0 text-danger"
              aria-hidden="true"
            />
          )}
          <span className="break-words font-medium">
            Broker execution allowed: {allowed ? "Yes" : "No"}
          </span>
        </div>
        <div className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2">
          <span className="text-muted-foreground">Status:</span>
          <Badge dot variant={badgeVariantForChainStatus(risk.status)}>
            {formatChainValue(risk.status)}
          </Badge>
        </div>
        <p className="break-words sm:col-span-2">
          <span className="text-muted-foreground">Rejection reasons:</span>{" "}
          {formatList(risk.rejection_reasons)}
        </p>
      </div>
      <SourceCitations citations={citations} />
    </div>
  );
}

function PositionSizingContent({
  citations,
  payload,
}: {
  citations: SourceCitation[];
  payload: PositionSizingPayload;
}) {
  const sizing = payload.position_sizing_decision;

  return (
    <div className="min-w-0 space-y-4 text-sm">
      <p className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 font-medium text-primary">
        <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
        Read-only. Quantity was code-decided.
      </p>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetadataItem label="Quantity" value={String(sizing.approved_quantity)} />
        <MetadataItem
          label="Risk budget"
          value={formatMoney(sizing.risk_budget)}
        />
        <MetadataItem
          label="Projected max loss"
          value={formatMoney(sizing.projected_max_loss)}
        />
        <MetadataItem
          label="Entry cost required"
          value={formatMoney(sizing.entry_cost_required)}
        />
      </dl>
      <p className="break-words text-muted-foreground">{sizing.explanation}</p>
      <SourceCitations citations={citations} />
    </div>
  );
}

function ExecutionProposalContent({
  payload,
}: {
  payload: ExecutionProposalPayload;
}) {
  const status = stringField(payload, "proposal_status");

  return (
    <div className="min-w-0 space-y-4 text-sm">
      <p className="flex items-center gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 font-medium text-primary">
        <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
        Read-only execution proposal payload.
      </p>
      {status ? (
        <p className="flex items-center gap-2">
          <span className="text-muted-foreground">Status:</span>
          <Badge variant={badgeVariantForChainStatus(status)}>
            {formatChainValue(status)}
          </Badge>
        </p>
      ) : null}
      <RawPayloadDetails label="Raw execution proposal" payload={payload} />
    </div>
  );
}

function OutcomeContent({ payload }: { payload: TradeOutcomePayload }) {
  const pnl = payload.outcome.net_realized_pnl;
  const pnlTone =
    typeof pnl === "number"
      ? pnl > 0
        ? "text-success"
        : pnl < 0
          ? "text-danger"
          : "text-foreground"
      : "text-foreground";

  return (
    <div className="min-w-0 space-y-4 text-sm">
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetadataItem
          label="Outcome"
          value={formatChainValue(payload.outcome.outcome_type)}
        />
        <MetadataItem
          label="Net PnL"
          value={formatMoney(payload.outcome.net_realized_pnl)}
          valueClassName={cn("font-semibold tabular-nums", pnlTone)}
        />
        <MetadataItem
          label="Open quantity"
          value={String(payload.outcome.open_quantity ?? "-")}
        />
        <MetadataItem
          label="Closed quantity"
          value={String(payload.outcome.closed_quantity ?? "-")}
        />
      </dl>
      <p className="break-words text-muted-foreground">
        Reasons: {formatList(payload.outcome.outcome_reasons)}
      </p>
    </div>
  );
}

function MetadataItem({
  label,
  value,
  valueClassName,
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-background px-3 py-2">
      <dt className="text-[0.6875rem] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className={cn("mt-1 break-words text-sm text-foreground", valueClassName)}>
        {value}
      </dd>
    </div>
  );
}

function RawPayloadDetails({
  label,
  payload,
}: {
  label: string;
  payload: unknown;
}) {
  return (
    <details className="rounded-card border border-border bg-background p-3">
      <summary className="cursor-pointer font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
        {label}
      </summary>
      <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-card border border-border bg-card p-3 font-mono text-xs text-foreground">
        {formatJson(payload)}
      </pre>
    </details>
  );
}

function getRecordStatus(record: DecisionChainRecord): string {
  if (!record.payload.ok) {
    return "malformed";
  }

  switch (record.recordType) {
    case "strategy_decision":
      return (record.payload.data as StrategyDecisionPayload).strategy_decision
        .status;
    case "analyst_review":
      return (record.payload.data as AnalystReviewPayload).status;
    case "risk_decision":
      return (record.payload.data as RiskDecisionPayload).risk_gate_decision
        .status;
    case "position_sizing":
      return (record.payload.data as PositionSizingPayload)
        .position_sizing_decision.status;
    case "execution_proposal":
      return (
        stringField(record.payload.data as ExecutionProposalPayload, "proposal_status") ??
        "recorded"
      );
    case "trade_outcome":
    case "outcome_correction":
      return (record.payload.data as TradeOutcomePayload).outcome.outcome_type;
  }
}

function firstRecordMetadata(records: DecisionChainRecord[]) {
  const first = records.find(
    (record) => record.row.target || record.row.theme || record.row.run_id,
  )?.row;
  return {
    runId: first?.run_id ?? "unknown",
    target: first?.target ?? "Unknown target",
    theme: first?.theme ?? "unknown",
  };
}

function stringField(
  payload: ExecutionProposalPayload,
  key: string,
): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? String(value);
}
