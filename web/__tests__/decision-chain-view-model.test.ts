import { describe, expect, it } from "vitest";
import {
  buildAnalystReviewViewModel,
  buildDecisionChainViewModel,
  buildExecutionProposalViewModel,
  buildPositionSizingViewModel,
  buildStrategyEvidenceViewModel,
} from "@/features/decisions/decision-chain-view-model";
import { parseDecisionChain } from "@/features/decisions/parse-decision-chain";
import {
  analystPayload,
  executionPayload,
  journalRow,
  outcomePayload,
  positionSizingPayload,
  riskPayload,
  strategyPayload,
} from "./decision-chain-fixtures";

describe("decision chain view model", () => {
  it("derives header badges from parsed chain records", () => {
    const view = buildDecisionChainViewModel(chainRecords());

    expect(view.header).toEqual({
      executionMode: "propose_only",
      outcome: "pending",
      runId: "scheduled:2026-06-01",
      strategyStatus: "candidate_ready_for_analyst",
      target: "NTNX",
      theme: "AI_STORAGE",
    });
  });

  it("maps strategy evidence from the current candidate brief contract", () => {
    const evidence = buildStrategyEvidenceViewModel(strategyPayload);

    expect(evidence).toMatchObject({
      direction: "bullish",
      earningsDate: "2026-06-03",
      expression: "defined-risk bullish call spread",
      peerSignalScoreLabel: "0.82",
      positivePeerRatioLabel: "75%",
      reportTime: "after_close",
      reportedPeersLabel: "PSTG, DELL",
      status: "candidate_ready_for_analyst",
      thesis: "Bullish AI_STORAGE read-through for NTNX.",
    });
    expect(evidence.supportingEvidence).toEqual([
      "Peer reports cited stronger enterprise storage demand.",
    ]);
    expect(evidence.peerScores).toEqual([
      {
        missingFactorsLabel: "-",
        negativeFactorsLabel: "-",
        positiveFactorsLabel: "AI storage demand",
        scoreLabel: "0.8",
        ticker: "PSTG",
      },
    ]);
  });

  it("labels analyst conviction without turning it into trade confidence", () => {
    const analyst = buildAnalystReviewViewModel(analystPayload);

    expect(analyst).toMatchObject({
      analystConvictionLabel: "0.68",
      citedCitationIdsLabel: "citation-1",
      recommendation: "support",
      suggestedExpression: "defined-risk bullish call spread",
    });
    expect(Object.keys(analyst).join(" ")).not.toMatch(/\bconfidence\b/i);
  });

  it("maps position sizing detail and Claude override flags", () => {
    const sizing = buildPositionSizingViewModel(positionSizingPayload);

    expect(sizing).toMatchObject({
      accountEquityLabel: "$100,000.00",
      approvedQuantityLabel: "4",
      claudePresentLabel: "Yes",
      claudeSizingOverrideAttemptedLabel: "No",
      entryCostRequiredLabel: "$980.00",
      projectedMaxLossLabel: "$1,000.00",
      riskBudgetLabel: "$1,000.00",
      unitMaxLossLabel: "$250.00",
    });
  });

  it("extracts only available execution leg fields", () => {
    const execution = buildExecutionProposalViewModel(executionPayload);

    expect(execution).toEqual({
      legs: [
        {
          quantity: "4",
          side: "long",
          symbol: "NTNX 2026-06-19 55C",
        },
      ],
      status: "proposed",
    });
  });
});

function chainRecords() {
  return parseDecisionChain([
    journalRow({
      created_at: "2026-06-01T14:30:00Z",
      journal_record_id: "journal-strategy",
      payload: strategyPayload,
      record_type: "strategy_decision",
    }),
    journalRow({
      created_at: "2026-06-01T14:33:00Z",
      journal_record_id: "journal-analyst",
      payload: analystPayload,
      record_type: "analyst_review",
    }),
    journalRow({
      created_at: "2026-06-01T14:35:00Z",
      journal_record_id: "journal-risk",
      payload: riskPayload,
      record_type: "risk_decision",
    }),
    journalRow({
      created_at: "2026-06-01T14:40:00Z",
      journal_record_id: "journal-sizing",
      payload: positionSizingPayload,
      record_type: "position_sizing",
    }),
    journalRow({
      created_at: "2026-06-01T14:45:00Z",
      journal_record_id: "journal-execution",
      payload: executionPayload,
      record_type: "execution_proposal",
    }),
    journalRow({
      created_at: "2026-06-01T14:50:00Z",
      journal_record_id: "journal-outcome",
      payload: outcomePayload,
      record_type: "trade_outcome",
    }),
  ]);
}
