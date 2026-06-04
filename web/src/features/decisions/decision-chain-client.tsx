"use client";

import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { DecisionChainView } from "./decision-chain-view";
import { useDecisionChain } from "./use-decision-chain";

export function DecisionChainClient({ decisionId }: { decisionId: string }) {
  const decisionChain = useDecisionChain(decisionId);

  if (decisionChain.isPending) {
    return <LoadingState label="Loading decision chain..." />;
  }

  if (decisionChain.error) {
    return <ErrorState title={decisionChain.error.message} />;
  }

  if (!decisionChain.data || decisionChain.data.length === 0) {
    return <EmptyState message="No journal records for this decision." />;
  }

  return (
    <DecisionChainView
      decisionId={decisionId}
      records={decisionChain.data}
    />
  );
}
