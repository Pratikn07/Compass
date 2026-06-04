import type { z } from "zod";
import type { Database } from "@/lib/supabase/database.types";
import type {
  AnalystReviewPayloadSchema,
  ExecutionProposalPayloadSchema,
  PositionSizingPayloadSchema,
  RiskDecisionPayloadSchema,
  StrategyDecisionPayloadSchema,
  TradeOutcomePayloadSchema,
} from "./decision-chain-schemas";

export type JournalRecordRow =
  Database["prescient_storage"]["Tables"]["journal_records"]["Row"];

export type DecisionChainRecordType =
  | "strategy_decision"
  | "analyst_review"
  | "risk_decision"
  | "position_sizing"
  | "execution_proposal"
  | "trade_outcome"
  | "outcome_correction";

export type SourceCitation = {
  citation_id: string;
  provider: string;
  source_type: string;
  title?: string | null;
  url?: string | null;
  source_endpoint?: string | null;
  source_id?: string | null;
  as_of?: string | null;
  retrieved_at?: string | null;
  excerpt?: string | null;
  confidence?: string;
};

export type StrategyDecisionPayload = z.infer<
  typeof StrategyDecisionPayloadSchema
>;
export type AnalystReviewPayload = z.infer<typeof AnalystReviewPayloadSchema>;
export type RiskDecisionPayload = z.infer<typeof RiskDecisionPayloadSchema>;
export type PositionSizingPayload = z.infer<
  typeof PositionSizingPayloadSchema
>;
export type ExecutionProposalPayload = z.infer<
  typeof ExecutionProposalPayloadSchema
>;
export type TradeOutcomePayload = z.infer<typeof TradeOutcomePayloadSchema>;

export type ParsedPayload =
  | StrategyDecisionPayload
  | AnalystReviewPayload
  | RiskDecisionPayload
  | PositionSizingPayload
  | ExecutionProposalPayload
  | TradeOutcomePayload;

export type PayloadParseResult =
  | { ok: true; data: ParsedPayload; citations: SourceCitation[] }
  | { ok: false; error: string; raw: unknown };

export type DecisionChainRecord = {
  row: JournalRecordRow;
  recordType: DecisionChainRecordType;
  label: string;
  order: number;
  payload: PayloadParseResult;
};
